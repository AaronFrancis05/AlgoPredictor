import type { MetadataRoute } from "next";

import { site } from "@/lib/site";

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  const pages: [string, MetadataRoute.Sitemap[number]["changeFrequency"], number][] = [
    ["/", "daily", 1],
    ["/pricing", "weekly", 0.9],
    ["/track-record", "daily", 0.9],
    ["/how-it-works", "monthly", 0.7],
    ["/responsible-gambling", "yearly", 0.4],
    ["/legal/terms", "yearly", 0.2],
    ["/legal/privacy", "yearly", 0.2],
  ];
  return pages.map(([path, changeFrequency, priority]) => ({
    url: `${site.url}${path}`, lastModified: now, changeFrequency, priority,
  }));
}
