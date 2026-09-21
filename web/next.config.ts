import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Verdicts change only when the pipeline runs and reloads the table, so
  // pages are rendered per request against Supabase rather than cached at
  // build time: a reload after a load shows the new run without a rebuild.
  typedRoutes: true,
};

export default nextConfig;
