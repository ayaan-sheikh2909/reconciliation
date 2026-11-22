-- ERP movements renamed into the shared silver schema; no business logic here
select
    erp_doc_number,
    line_item_number,
    item_code as sku,
    warehouse_code,
    qty_delta as movement_qty,
    cast(posting_date as timestamp) as movement_date,
    doc_type as event_type,
    'ERP' as source_system
from "reconciliation"."bronze"."erp_feed"