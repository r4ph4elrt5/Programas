import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { DOMParser } from "linkedom";
import { analyzeDocument, analyzeSnapshot } from "../snapshot.mjs";

globalThis.document = new DOMParser().parseFromString("<!doctype html><html><body></body></html>", "text/html");
const fixture = (name) => readFileSync(new URL(`./fixtures/${name}.html`, import.meta.url), "utf8");
const ready = fixture("uploaded-ready");

test("uploading is not completed even when progress reaches 100%", () => {
  const result = analyzeSnapshot(fixture("uploading").replaceAll("40%", "100%"));
  assert.equal(result.upload, "uploading");
  assert.equal(result.canSubmit, false);
  assert.equal(result.confirmation, "unverified");
});

test("uploaded and checks pending never means ready or published", () => {
  const result = analyzeSnapshot(fixture("uploaded-checking"));
  assert.equal(result.upload, "uploaded");
  assert.equal(result.checks, "pending");
  assert.equal(result.canSubmit, false);
  assert.equal(result.confirmation, "unverified");
});

test("inactive error/checking templates are ignored", () => {
  const result = analyzeSnapshot(ready);
  assert.equal(result.upload, "uploaded");
  assert.equal(result.checks, "passed");
  assert.equal(result.canSubmit, true);
  assert.equal(result.confirmation, "unverified");
  assert.match(result.message, /não confirma publicação nem agendamento/);
});

for (const attribute of ["disabled", 'disabled="false"', 'aria-disabled="true"',
  'data-disabled="true"', 'data-loading="true"', 'aria-busy="true"']) {
  test(`final button gate ${attribute} is honored`, () => {
    const html = ready.replace('aria-disabled="false" data-disabled="false" data-loading="false"', attribute);
    assert.equal(analyzeSnapshot(html).canSubmit, false);
  });
}

for (const hidden of ["hidden", "inert", 'aria-hidden="true"', 'data-show="false"',
  'style="display:none"', 'style="visibility:hidden !important"', 'style="content-visibility:hidden"']) {
  test(`hidden submit ancestor ${hidden} is honored`, () => {
    const html = ready.replace('<button data-e2e="post_video_button"', `<div ${hidden}><button data-e2e="post_video_button"`)
      .replace("Agendar</button>", "Agendar</button></div>");
    assert.equal(analyzeSnapshot(html).canSubmit, false);
  });
}

test("disabled fieldset prevents submission", () => {
  const html = ready.replace('<button data-e2e="post_video_button"', '<fieldset disabled><button data-e2e="post_video_button"')
    .replace("Agendar</button>", "Agendar</button></fieldset>");
  assert.equal(analyzeSnapshot(html).canSubmit, false);
});

test("an active warning/error takes precedence over other successful checks", () => {
  for (const state of ["status-error", "status-warn"]) {
    const result = analyzeSnapshot(ready + `<div class="status-result ${state}" data-show="true">Revisar</div>`);
    assert.equal(result.checks, "blocked");
    assert.equal(result.canSubmit, false);
  }
});

test("missing and ambiguous upload roots fail closed", () => {
  assert.equal(analyzeSnapshot("<p>Enviado</p>").upload, "unknown");
  assert.equal(analyzeSnapshot(ready + ready).upload, "unknown");
  assert.equal(analyzeSnapshot(ready + ready).canSubmit, false);
});

test("progress success alone does not prove upload completed", () => {
  const html = ready.replace(/<div class="info-status success">.*?<\/div>/, "");
  assert.equal(analyzeSnapshot(html).upload, "unknown");
  assert.equal(analyzeSnapshot(html).canSubmit, false);
});

test("fallback info-body excerpt works without generated jsx classes", () => {
  const result = analyzeSnapshot(ready.replace('data-e2e="upload_status_container"', 'class="info-body"'));
  assert.equal(result.upload, "uploaded");
  assert.equal(result.confirmation, "unverified");
});

test("pasted scripts are inert and markup is never inserted into the panel", () => {
  globalThis.snapshotScriptRan = false;
  const result = analyzeSnapshot(ready + '<script>globalThis.snapshotScriptRan=true</script>');
  assert.equal(globalThis.snapshotScriptRan, false);
  assert.equal(result.confirmation, "unverified");
  delete globalThis.snapshotScriptRan;
});

test("input is bounded and invalid documents rejected", () => {
  assert.throws(() => analyzeSnapshot(""), TypeError);
  assert.throws(() => analyzeSnapshot("x".repeat(2_000_001)), RangeError);
  assert.throws(() => analyzeDocument({}), TypeError);
});
