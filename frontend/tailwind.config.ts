import type { Config } from "tailwindcss";

/**
 * Grayish-Blue 미니멀 테마 토큰.
 * 컴포넌트는 색을 하드코딩하지 않고 여기 정의된 토큰만 쓴다(CLAUDE.md §4, 03 §2).
 * 색을 바꾸려면 이 파일만 고친다.
 */
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // 회청색(Grayish-Blue) 스케일 — 배경·테두리·텍스트 위계
        surface: {
          DEFAULT: "#f7f9fb", // 페이지 배경
          card: "#ffffff",     // 카드 배경
          muted: "#eef2f6",    // 옅은 구역
        },
        border: {
          DEFAULT: "#dbe2ea",
        },
        content: {
          DEFAULT: "#2a3441", // 본문 텍스트
          muted: "#5b6b7d",   // 보조 텍스트
          subtle: "#8896a5",  // 라벨/캡션
        },
        // 강조색 (회청 톤의 blue)
        accent: {
          DEFAULT: "#4a6fa5",
          hover: "#3d5c8a",
          soft: "#e3ebf5",
        },
        // 상태색 (Job/진행률용)
        status: {
          ok: "#3f8f6b",
          warn: "#c08a2d",
          error: "#c0503f",
        },
        // 대시보드 KPI 카드 등, 카드별로 구분이 필요할 때 순서대로 돌려 쓰는 톤 팔레트.
        chip: {
          1: "#D1EAF0",
          2: "#BCD4E6",
          3: "#8BA8B7",
          4: "#AFDBF5",
        },
      },
    },
  },
  plugins: [],
};

export default config;
