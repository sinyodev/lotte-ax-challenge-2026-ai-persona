import { lazy, Suspense } from "react"
import { Navigate, Route, Routes } from "react-router"
import { InternationalizationProvider } from "@astryxdesign/core/i18n"
import { LinkProvider } from "@astryxdesign/core/Link"
import koKR from "@astryxdesign/core/locales/ko-KR.generated.js"
import { Theme } from "@astryxdesign/core/theme"
import { defaultThemeSlug, themes } from "./astryx-themes"
import { copy } from "./copy"
import { AppFrame } from "./components/AppFrame"
import { RouterLink } from "./components/RouterLink"
import { DesignPage } from "./pages/DesignPage"
import { HomePage } from "./pages/HomePage"
import { PlaceholderPage } from "./pages/PlaceholderPage"
import { ProposalPage } from "./pages/ProposalPage"
import { ConceptPage, TestPage } from "./pages/TestPage"
import { TrendsPage } from "./pages/TrendsPage"
import { IdeasPage } from "./pages/IdeasPage"

// 입체 매장은 여는 때에만 받는다(three와 그 도구가 다른 화면의 묶음에 섞이지 않게).
const StorePage = lazy(() => import("./store3d/StorePage"))
const AnalysisProtoPage = lazy(() => import("./proto/board-analysis/BoardAnalysisProtoPage"))
const W7ProtoPage = lazy(() => import("./proto/w7/W7ProtoPage"))
const W6ProtoPage = lazy(() => import("./proto/w6/W6ProtoPage"))
const ResultProtoPage = lazy(() => import("./proto/result/ResultProtoPage"))
const FollowupProtoPage = lazy(() => import("./proto/followup/FollowupProtoPage"))

function FramedRoutes() {
  return (
    <AppFrame>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/trends" element={<TrendsPage />} />
        <Route path="/ideas" element={<IdeasPage />} />
        <Route
          path="/store"
          element={
            <Suspense fallback={null}>
              <StorePage />
            </Suspense>
          }
        />
        <Route path="/shelf" element={<Navigate to="/store" replace />} />
        <Route path="/panel" element={<PlaceholderPage {...copy.pages.panel} />} />
        <Route path="/reliability" element={<PlaceholderPage {...copy.pages.reliability} />} />
        <Route path="/concept/:id" element={<ConceptPage />} />
        <Route path="/test/new" element={<TestPage />} />
        <Route path="/test/:id" element={<TestPage />} />
      </Routes>
    </AppFrame>
  )
}

export default function App() {
  return (
    <InternationalizationProvider locale="ko-KR" messages={{ "ko-KR": koKR }}>
      <Theme theme={themes[defaultThemeSlug]} mode="light">
        <LinkProvider component={RouterLink}>
          <Routes>
            {/* 견본 페이지는 왼쪽 메뉴에 넣지 않는다. */}
            <Route path="/proto/analysis" element={<Suspense fallback={null}><AnalysisProtoPage /></Suspense>} />
            <Route path="/design" element={<DesignPage />} />
            <Route path="/proto/w7" element={<Suspense fallback={null}><W7ProtoPage /></Suspense>} />
            <Route path="/proto/w6" element={<Suspense fallback={null}><W6ProtoPage /></Suspense>} />
            <Route path="/proto/result" element={<Suspense fallback={null}><ResultProtoPage /></Suspense>} />
            <Route path="/proto/followup" element={<Suspense fallback={null}><FollowupProtoPage /></Suspense>} />
            {/* 14: 신제품 제안서는 왼쪽 메뉴 없이 종이만 */}
            <Route path="/proposal/:chatId" element={<ProposalPage />} />
            <Route path="*" element={<FramedRoutes />} />
          </Routes>
        </LinkProvider>
      </Theme>
    </InternationalizationProvider>
  )
}
