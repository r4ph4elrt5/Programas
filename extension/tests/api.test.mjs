import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {BASE_URL, BridgeError, makeClient as createClient, scheduledInstant, validSession} from "../api.mjs";

const makeClient = (fetcher) => createClient(fetcher, "a".repeat(32));

const future = new Date(Date.now() + 3600_000).toISOString();

test("session is valid only before expiry", () => {
  assert.equal(validSession({token: "x".repeat(48), expires_at: future}), true);
  assert.equal(validSession({token: "short", expires_at: future}), false);
  assert.equal(validSession({token: "x".repeat(48), expires_at: "2000-01-01"}), false);
  assert.equal(validSession(null), false);
  assert.equal(validSession({token: "x".repeat(48) + "\r\n", expires_at: future}), false);
  assert.equal(validSession({token: "x".repeat(257), expires_at: future}), false);
});

test("a real extension identity is required before local communication", () => {
  assert.throws(() => createClient(async () => {}, "not-an-extension"), BridgeError);
  assert.throws(() => createClient(async () => {}, ""), BridgeError);
});

test("manifest grants no TikTok page, cookie or injection access", () => {
  const manifest = JSON.parse(readFileSync(new URL("../manifest.json", import.meta.url), "utf8"));
  assert.deepEqual(manifest.permissions.toSorted(), ["clipboardWrite", "sidePanel", "storage"].toSorted());
  assert.deepEqual(manifest.host_permissions, ["http://127.0.0.1:8765/*"]);
  assert.equal(manifest.content_scripts, undefined);
  assert.equal(manifest.externally_connectable, undefined);
  assert.match(manifest.content_security_policy.extension_pages, /frame-src 'none'/);
  assert.match(manifest.content_security_policy.extension_pages, /default-src 'self'/);
});

test("pairing uses fixed loopback and never forwards cookies or redirects", async () => {
  const calls = [];
  const client = makeClient(async (url, options) => {
    calls.push([url, options]);
    return {ok: true, json: async () => ({token: "x".repeat(48), expires_at: future, extra: "ignored"})};
  });
  assert.deepEqual(await client.pair("12345678"), {token: "x".repeat(48), expires_at: future});
  const [url, options] = calls[0];
  assert.equal(url, BASE_URL + "/companion/pair");
  assert.equal(options.credentials, "omit");
  assert.equal(options.redirect, "error");
  assert.equal(options.headers.Authorization, undefined);
  assert.equal(options.headers["X-MultiPost-Extension"], "a".repeat(32));
  assert.equal(options.body, '{"code":"12345678"}');
});

test("invalid pair code makes no request", async () => {
  const client = makeClient(() => { throw new Error("unexpected network"); });
  await assert.rejects(client.pair("1234"), BridgeError);
});

test("jobs require the assisted mode and use only scoped bearer", async () => {
  const client = makeClient(async (url, options) => {
    assert.equal(url, BASE_URL + "/companion/jobs");
    assert.equal(options.headers.Authorization, "Bearer scoped-session");
    return {ok: true, json: async () => ({jobs: [{id: "one"}], mode: "ASSISTED_PUBLISH"})};
  });
  assert.deepEqual(await client.jobs("scoped-session"), [{id: "one"}]);
  await assert.rejects(makeClient(async () => ({ok: true, json: async () => ({jobs: [], mode: "AUTO_PUBLISH"})})).jobs("token"), BridgeError);
});

test("confirmation rejects a path injection and forwards a valid manual declaration", async () => {
  let seen;
  const client = makeClient(async (url, options) => {
    seen = [url, JSON.parse(options.body)];
    return {ok: true, json: async () => ({status: "USER_SCHEDULED"})};
  });
  assert.throws(() => client.confirm("token", "../../jobs", {}), BridgeError);
  const body = {outcome: "scheduled", scheduled_at: future, url: ""};
  assert.equal((await client.confirm("token", "a123", body)).status, "USER_SCHEDULED");
  assert.deepEqual(seen, [BASE_URL + "/companion/jobs/a123/confirm", body]);
});

test("server errors never expose a response body", async () => {
  let parsed = false;
  const client = makeClient(async () => ({ok: false, status: 401, json: async () => { parsed = true; return {token: "secret"}; }}));
  await assert.rejects(client.jobs("token"), (error) => error.status === 401 && !error.message.includes("secret"));
  assert.equal(parsed, false);
});

test("local scheduling requires a future real time", () => {
  assert.equal(scheduledInstant("2027-01-01T12:00:00Z", Date.parse("2026-01-01")), "2027-01-01T12:00:00.000Z");
  assert.throws(() => scheduledInstant("invalid"), BridgeError);
  assert.throws(() => scheduledInstant("2000-01-01"), BridgeError);
});
