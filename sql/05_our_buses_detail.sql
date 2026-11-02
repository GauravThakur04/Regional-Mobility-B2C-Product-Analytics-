-- Our buses only (ticket_ticketnew.source = 1): extra fields not in 01_tickets.sql.
-- Bus / operator: ticket.service_id → bus_search_service.id → bus_number → replica_data_busreplica
-- (latest row per bus number, so the join stays 1:1).
WITH bus AS (
    SELECT DISTINCT ON (number) number, operator_name, is_pos_connected, is_air_conditioned, category
    FROM replica_data_busreplica
    ORDER BY number, updated_at DESC
)
SELECT
    t.id                                               AS ticket_id,
    t.ticket_sourcing,
    t.created_at AT TIME ZONE 'Asia/Kolkata'           AS booked_at,
    t.total_amount,
    t.total_discount,
    t.refund_amount,
    t.cancelled_by,
    t.distance_in_km,
    t.trip_number,
    t.sent_to_pos,
    s.bus_number,
    coalesce(m.operator_name, b.operator_name)         AS operator,
    b.is_pos_connected                                 AS bus_has_machine,
    b.is_air_conditioned                               AS bus_ac
FROM ticket_ticketnew t
LEFT JOIN ticket_ticketmeta m  ON m.ticket_id = t.id
LEFT JOIN bus_search_service s ON s.id::text = t.service_id
LEFT JOIN bus b                ON b.number = s.bus_number
WHERE t.source = 1;
