"""Bounded rolling Workday API pages, with durable successful-page checkpoints.

Offsets are not snapshot tokens. A resumed inventory therefore never proves
closure. The first page is always checked for fresh postings; a bounded rolling
window covers older pages without retaining a giant JSON inventory.
"""
from datetime import datetime, timezone


async def workday_pages(client, url, first, headers, source, cache):
    from .discovery import _request, DiscoveryError
    rows = list(first.get("jobPostings", []))
    total = max(0, int(first.get("total", 0)))
    checkpoint = source.get("_pagination_checkpoint", cache.get("pagination", {})) or {}
    rows = list(checkpoint.get("pending_rows", [])) + rows
    offset = max(20, min(int(checkpoint.get("offset", 20)), max(20, total)))
    if offset >= total:
        offset = 20
    resumed = offset > 20
    error_delay = None
    pages = 1
    async def save(value):
        callback = source.get("_save_checkpoint")
        if callback:
            await callback({"offset":value,"pending_rows":rows,"updated_at":datetime.now(timezone.utc).isoformat()})
    while offset < total and pages < 4 and len(rows) < 160:
        try:
            response = await _request(client, url, headers={k:v for k,v in headers.items() if not k.lower().startswith("if-")}, method="POST",
                payload={"appliedFacets":{},"limit":20,"offset":offset,"searchText":"intern"})
            data = response.json()
            page = data.get("jobPostings")
            if not isinstance(page, list) or not page:
                raise DiscoveryError("Pagination schema/coverage changed; previous inventory preserved")
        except (DiscoveryError, ValueError, TypeError) as exc:
            # Retain the exact failed offset. Successful pages remain useful,
            # but this response cannot mark absent opportunities closed.
            await save(offset)
            error_delay = max(60, int(getattr(exc, "retry_after", 0) or 0))
            break
        rows.extend(page)
        offset += len(page)
        pages += 1
        await save(20 if offset >= total else offset)
    partial = resumed or offset < total or error_delay is not None
    rows = list({str(row.get("externalPath")):row for row in rows}.values())
    return {**first,"jobPostings":rows}, {"offset":20 if offset >= total else offset}, partial, error_delay
