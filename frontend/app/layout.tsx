import "./globals.css";
import type { Metadata } from "next";
export const metadata: Metadata = {
  title: "GalStudy · 与知识，怦然相遇",
  description: "把你的课件，变成属于你的学习故事。",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
