// Monaco from our own bundle. @monaco-editor/react otherwise fetches it from
// cdn.jsdelivr.net at runtime: the SQL editor then needs internet, and runs a
// Monaco (and the DOMPurify inside it) that npm audit never sees.
import * as monaco from 'monaco-editor';
import { loader } from '@monaco-editor/react';

// The SQL editor only needs the base editor worker; no language here has a
// worker of its own.
self.MonacoEnvironment = {
  getWorker: () =>
    new Worker(new URL('monaco-editor/editor/editor.worker', import.meta.url)),
};

loader.config({ monaco });
