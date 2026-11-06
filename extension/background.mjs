// This extension never injects code into TikTok or reads a platform session.
chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setPanelBehavior({openPanelOnActionClick: true}).catch(() => {});
});

chrome.action.onClicked.addListener((tab) => {
  chrome.sidePanel.open({windowId: tab.windowId}).catch(() => {
    // A normal extension tab is available when a browser cannot show a side panel.
    chrome.tabs.create({url: chrome.runtime.getURL("panel.html")});
  });
});
