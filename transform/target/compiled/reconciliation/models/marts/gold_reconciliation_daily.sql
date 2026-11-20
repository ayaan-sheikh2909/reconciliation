-- SKU x warehouse x day reconciliation: the single view that answers which
-- number to trust, and by how much the two systems disagree.
with erp_daily as (
    select
        sku,
        warehouse_code,
        date_trunc('day', movement_date) as day,
        sum(movement_qty) as erp_qty
    from "reconciliation"."silver"."stg_erp_movements"
    group by 1, 2, 3
),

wms_daily as (
    select
        sku,
        warehouse_code,
        date_trunc('day', movement_date) as day,
        sum(movement_qty) as wms_qty
    from "reconciliation"."silver"."stg_wms_movements"
    group by 1, 2, 3
)

select
    coalesce(erp_daily.sku, wms_daily.sku) as sku,
    coalesce(erp_daily.warehouse_code, wms_daily.warehouse_code) as warehouse_code,
    coalesce(erp_daily.day, wms_daily.day) as day,
    coalesce(erp_daily.erp_qty, 0) as erp_qty,
    coalesce(wms_daily.wms_qty, 0) as wms_qty,
    -- positive variance means WMS recorded more movement than ERP expected
    coalesce(wms_daily.wms_qty, 0) - coalesce(erp_daily.erp_qty, 0) as variance,
    coalesce(wms_daily.wms_qty, 0) - coalesce(erp_daily.erp_qty, 0) != 0 as has_discrepancy
from erp_daily
full outer join wms_daily
    on erp_daily.sku = wms_daily.sku
    and erp_daily.warehouse_code = wms_daily.warehouse_code
    and erp_daily.day = wms_daily.day