-- WMS movements renamed into the shared silver schema. units and qty_delta are
-- both the same underlying movement_qty column from the source ledger, so this
-- is a straight rename, no sign flipping or vocabulary mapping needed.
select
    row_id,
    sku,
    warehouse_code,
    units as movement_qty,
    cast(event_date as timestamp) as movement_date,
    event_type,
    'WMS' as source_system
from "reconciliation"."bronze"."wms_feed"