import type {
  ContentSupportStatus,
  ExternalSource,
  ExternalSourceStatus,
  SourceLinkStatus,
} from "../api/types";

/**
 * John MVP Final Gap Closure -- Structured External Source Traceability.
 *
 * Renders only fields the upstream source actually supplied
 * (comqutor_alpha.source_provenance.public_source_fields) -- never a
 * fabricated placeholder. A clickable URL is shown only when the source
 * itself carries a genuine `url`. Never renders `claim_id` or any other
 * internal identifier here -- those stay in each caller's own Technical
 * Details disclosure, so an internal id can never visually pass as an
 * external citation.
 *
 * T1 source-linking chain (COMQUTOR Alpha next-round task, 2026-09-26):
 * `linkedSource`/`sourceLinkStatus`/`contentSupportStatus` are the NEW,
 * ID-validated fields (comqutor_alpha.structure_engine.
 * structured_output_adapter._annotate_source_link) -- deliberately kept
 * and rendered SEPARATELY from `source`/`status` above (the legacy,
 * read-time title-match join): a valid link (`sourceLinkStatus ===
 * "VALID"`) never implies the source's content actually supports the
 * claim -- `contentSupportStatus` is always shown alongside it, and is
 * "PENDING_REVIEW" for every claim linked so far (offline content
 * matching can prove linkage, not semantic support).
 */

const STATUS_LABELS: Record<ExternalSourceStatus, string> = {
  TRACEABLE: "Source",
  PARTIAL: "Source (partial)",
  UNAVAILABLE: "Source",
};

const SOURCE_LINK_STATUS_LABELS: Record<SourceLinkStatus, string> = {
  VALID: "Linked source",
  UNKNOWN_ID: "Source reference not recognized",
  CONTENT_UNAVAILABLE: "Source identity known, no captured content",
  TIME_INVALID: "Source published after the evidence cutoff",
  NOT_PROVIDED: "No source reference",
};

const CONTENT_SUPPORT_STATUS_LABELS: Record<ContentSupportStatus, string> = {
  SUPPORTS: "Supports this claim",
  OPPOSES: "Opposes this claim",
  BACKGROUND: "Background only",
  CITATION_ONLY: "Citation only",
  CONDITIONAL: "Conditional support",
  PENDING_REVIEW: "Support pending review",
  NOT_APPLICABLE: "Not applicable",
};

function LinkedSourceDisplay({
  linkedSource,
  sourceLinkStatus,
  contentSupportStatus,
}: {
  linkedSource: ExternalSource | null | undefined;
  sourceLinkStatus: SourceLinkStatus | null | undefined;
  contentSupportStatus: ContentSupportStatus | null | undefined;
}) {
  if (!sourceLinkStatus || sourceLinkStatus === "NOT_PROVIDED") {
    return null;
  }
  return (
    <div className="linked-source-display">
      <p className="linked-source-link-status">
        {SOURCE_LINK_STATUS_LABELS[sourceLinkStatus]}
      </p>
      {sourceLinkStatus === "VALID" && linkedSource ? (
        <>
          {linkedSource.title ? (
            <p className="linked-source-title">{linkedSource.title}</p>
          ) : null}
          {linkedSource.excerpt ? (
            <p className="linked-source-excerpt">&ldquo;{linkedSource.excerpt}&rdquo;</p>
          ) : null}
          {linkedSource.url ? (
            <a
              className="linked-source-link"
              href={linkedSource.url}
              target="_blank"
              rel="noopener noreferrer"
            >
              Open source
            </a>
          ) : null}
          {contentSupportStatus ? (
            <p className="linked-source-support-status">
              {CONTENT_SUPPORT_STATUS_LABELS[contentSupportStatus]}
            </p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

export function ExternalSourceDisplay({
  source,
  status,
  linkedSource,
  sourceLinkStatus,
  contentSupportStatus,
}: {
  source: ExternalSource | null | undefined;
  status: ExternalSourceStatus | undefined;
  linkedSource?: ExternalSource | null;
  sourceLinkStatus?: SourceLinkStatus | null;
  contentSupportStatus?: ContentSupportStatus | null;
}) {
  const effectiveStatus: ExternalSourceStatus = status ?? "UNAVAILABLE";
  const linkedSourceSection = (
    <LinkedSourceDisplay
      linkedSource={linkedSource}
      sourceLinkStatus={sourceLinkStatus}
      contentSupportStatus={contentSupportStatus}
    />
  );

  if (effectiveStatus === "UNAVAILABLE" || !source) {
    return (
      <div className="external-source-display external-source-unavailable">
        <p>External source metadata is not available for this finding.</p>
        {linkedSourceSection}
      </div>
    );
  }

  return (
    <div className="external-source-display external-source-present">
      <p className="external-source-label">{STATUS_LABELS[effectiveStatus]}</p>
      <dl className="external-source-fields">
        {source.name ? (
          <div className="external-source-row">
            <dt>Publisher</dt>
            <dd>{source.name}</dd>
          </div>
        ) : null}
        {source.title ? (
          <div className="external-source-row">
            <dt>Title</dt>
            <dd>{source.title}</dd>
          </div>
        ) : null}
        {source.published_at ? (
          <div className="external-source-row">
            <dt>Published</dt>
            <dd>{source.published_at}</dd>
          </div>
        ) : null}
        {source.external_record_id ? (
          <div className="external-source-row">
            <dt>Record</dt>
            <dd>{source.external_record_id}</dd>
          </div>
        ) : null}
        {source.locator ? (
          <div className="external-source-row">
            <dt>Locator</dt>
            <dd>{source.locator}</dd>
          </div>
        ) : null}
      </dl>
      {source.url ? (
        <a
          className="external-source-link"
          href={source.url}
          target="_blank"
          rel="noopener noreferrer"
        >
          Open source
        </a>
      ) : null}
      {effectiveStatus === "PARTIAL" ? (
        <p className="external-source-partial-note">
          Some source details are not available.
        </p>
      ) : null}
      {linkedSourceSection}
    </div>
  );
}
