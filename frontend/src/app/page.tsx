"use client";

import { Suspense } from "react";
import { ContentFilterToggles } from "@/components/content/content-filter-toggles";
import { SensitiveHiddenNotice } from "@/components/content/sensitive-hidden-notice";
import { InfiniteGallery } from "@/components/gallery/infinite-gallery";
import { useI18n } from "@/components/providers/locale-provider";
import { SwitchLabel } from "@/components/ui/switch-label";
import { useGalleryQueryControls } from "@/hooks/gallery/use-gallery-query-controls";

function HomeContent() {
  const { t } = useI18n();
  const {
    q,
    tokens,
    effectiveQuery,
    effectiveQueries,
    contentReady,
    multi,
    setMulti,
    collapseWorks,
    setCollapseWorks,
    onTagClick,
  } = useGalleryQueryControls();

  return (
    <div className="container py-6">
      <header className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">
          {q ? t("pages.home.searchTitle", { query: q }) : t("pages.home.title")}
        </h1>
        <div className="flex flex-wrap items-center justify-end gap-3">
          <ContentFilterToggles />
          <SwitchLabel label={t("pages.home.collapseWorks")} checked={collapseWorks} onChange={setCollapseWorks} />
          <SwitchLabel label={t("pages.home.multiSelect")} checked={multi} onChange={setMulti} />
        </div>
      </header>

      {!q && <SensitiveHiddenNotice className="mb-4" />}

      <InfiniteGallery
        query={effectiveQuery}
        queries={effectiveQueries}
        enabled={contentReady}
        activeTags={tokens}
        onTagClick={onTagClick}
        collapseWorks={collapseWorks}
      />
    </div>
  );
}

function HomeFallback() {
  const { t } = useI18n();
  return <div className="container py-6 text-sm text-muted-foreground">{t("common.loading")}</div>;
}

export default function HomePage() {
  return (
    <Suspense fallback={<HomeFallback />}>
      <HomeContent />
    </Suspense>
  );
}
