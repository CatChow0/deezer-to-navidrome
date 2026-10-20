import { showFlashMessages } from './core.js';
import { initVersion } from './version.js';
import { overlay } from './overlay.js';
import { initViews } from './views.js';
import { initActivity } from './activity.js';
import { initDownloads } from './downloads.js';
import { initSearch } from './search.js';
import { initPlaylists } from './playlists.js';
import { initAutomation } from './automation.js';
import { initLibrary } from './library.js';
import { initDedup } from './dedup.js';
import { initSettings } from './settings.js';

initViews();
initActivity();
initVersion();
showFlashMessages();

const drawer = overlay('drawer');
initDownloads();
initSearch(drawer);
initPlaylists(drawer);
initAutomation();
initLibrary();
initDedup(overlay('dedup-modal'));
initSettings();
