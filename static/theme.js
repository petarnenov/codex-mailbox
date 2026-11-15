'use strict';
// Blocking head script selects the stored preference before styles paint.
let savedTheme = 'dark';
try { savedTheme = localStorage.getItem('mailbox-theme') === 'light' ? 'light' : 'dark'; } catch (_) { /* Storage can be unavailable in private contexts. */ }
document.documentElement.dataset.theme = savedTheme;
