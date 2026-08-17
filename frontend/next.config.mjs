/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // NAS(시놀로지) 자체 호스팅용 — 실행에 필요한 것만 담은 출력을 만든다.
  // Vercel 배포는 이 값을 무시하므로 기존 배포에 영향이 없다(docs/20).
  output: "standalone",
};

export default nextConfig;
