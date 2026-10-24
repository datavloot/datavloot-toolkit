import './globals.css';

export const metadata = {
  title: "Crows Nest",
  description: 'Unified dashboard for the Optimist data platform',
};

// Applies the branding colours remembered by app/page.js before the first paint.
const applyRememberedBranding = `
  try {
    var v = JSON.parse(localStorage.getItem('cn-branding') || '{}');
    for (var k in v) document.documentElement.style.setProperty(k, v[k]);
  } catch (e) {}
`;

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <script dangerouslySetInnerHTML={{ __html: applyRememberedBranding }} />
      </head>
      <body className="min-h-screen bg-surface-1">
        {children}
      </body>
    </html>
  );
}
