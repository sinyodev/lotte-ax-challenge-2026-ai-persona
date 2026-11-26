import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "./src") },
    dedupe: ["react", "react-dom"],
  },
  // 처음 띄울 때 의존성을 뒤늦게 다시 묶으면 React가 두 벌 실려 화면이 한 번 깨진다. 미리 묶어 둔다.
  // Astryx 부품을 새로 불러 쓰면 여기에도 적는다.
  optimizeDeps: {
    include: [
      "react",
      "react-dom",
      "react-dom/client",
      "react/jsx-runtime",
      "react/jsx-dev-runtime",
      "react-router",
      "open-bot-avatar",
      "recharts",
      "open-bot-avatar/dom",
      "ai",
      "@ai-sdk/react",
      "zustand",
      "three",
      "three/addons/loaders/GLTFLoader.js",
      "three/addons/utils/SkeletonUtils.js",
      "@react-three/fiber",
      "@react-three/drei",
      "@astryxdesign/core/AlertDialog",
      "@astryxdesign/core/AppShell",
      "@astryxdesign/core/Avatar",
      "@astryxdesign/core/Badge",
      "@astryxdesign/core/Button",
      "@astryxdesign/core/Card",
      "@astryxdesign/core/Chat",
      "@astryxdesign/core/Collapsible",
      "@astryxdesign/core/Divider",
      "@astryxdesign/core/DropdownMenu",
      "@astryxdesign/core/EmptyState",
      "@astryxdesign/core/HStack",
      "@astryxdesign/core/Icon",
      "@astryxdesign/core/InfoTip",
      "@astryxdesign/core/IconButton",
      "@astryxdesign/core/Heading",
      "@astryxdesign/core/Item",
      "@astryxdesign/core/Link",
      "@astryxdesign/core/ProgressBar",
      "@astryxdesign/core/Table",
      "@astryxdesign/core/SegmentedControl",
      "@astryxdesign/core/SideNav",
      "@astryxdesign/core/Skeleton",
      "@astryxdesign/core/Spinner",
      "@astryxdesign/core/StatusDot",
      "@astryxdesign/core/Stepper",
      "@astryxdesign/core/Text",
      "@astryxdesign/core/TextArea",
      "@astryxdesign/core/Token",
      "@astryxdesign/core/Tooltip",
      "@astryxdesign/core/VStack",
      "@astryxdesign/core/i18n",
      "@astryxdesign/core/theme",
      "@heroicons/react/24/outline",
      "@heroicons/react/24/solid",
      "@heroicons/react/20/solid",
    ],
  },
  server: {
    port: 5173,
    strictPort: true,
    // 서버(app/server, FastAPI)는 8787에서 뜬다
    // 확인용으로 다른 서버를 가리킬 때는 환경 변수 AX_API를 준다(예: AX_API=http://127.0.0.1:8791)
    proxy: { "/api": process.env.AX_API ?? "http://127.0.0.1:8787" },
  },
})
