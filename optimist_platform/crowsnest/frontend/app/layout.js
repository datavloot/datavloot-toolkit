import './globals.css';

export const metadata = {
  title: "Crows Nest",
  description: 'Unified dashboard for the Optimist data platform',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-surface-1">
        {children}
      </body>
    </html>
  );
}
