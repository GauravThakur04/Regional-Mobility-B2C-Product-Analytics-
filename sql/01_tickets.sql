-- One row per ticket in ticket_ticketnew (all statuses; validity decided downstream).
-- Joins are 1:1: ticket_ticketmeta.ticket_id is UNIQUE, town ids are PKs, user_user.id is PK.
-- Customer key = md5(salt || phone) so no phone number leaves the database.
SELECT
    t.id                                            AS ticket_id,
    md5(%(salt)s || coalesce(u.contact::text, 'uid:' || t.user_id::text)) AS customer_key,
    t.user_id,
    coalesce(u.is_test_user, false)                 AS is_test_user,
    t.source,
    t.ticket_sourcing,
    t.ticket_with_pass,
    (t.pass_reward_id IS NOT NULL)                  AS has_pass_reward,
    t.status,
    t.refund_status,
    t.is_deleted,
    t.is_test_ticket,
    t.is_paid,
    (t.cancelled_on IS NOT NULL)                    AS has_cancelled_on,
    (t.reschedule_ticket_id IS NOT NULL)            AS is_rescheduled,
    t.pnr,
    t.service_id,
    t.payable_amount,
    CASE WHEN jsonb_typeof(t.seat_booked) = 'array' THEN jsonb_array_length(t.seat_booked) END AS seats,
    (t.created_at  AT TIME ZONE 'Asia/Kolkata')::date AS booking_date,
    (t.journey_date AT TIME ZONE 'Asia/Kolkata')::date AS journey_date,
    t.from_town_id,
    t.to_town_id,
    ft.name                                         AS from_town,
    tt.name                                         AS to_town,
    ft.district ->> 'name'                          AS from_district,
    tt.district ->> 'name'                          AS to_district,
    ft.district ->> 'state_name'                    AS from_state_raw,
    tt.district ->> 'state_name'                    AS to_state_raw,
    m.boarding_point_info ->> 'name'                AS boarding_stop_raw,
    m.drop_point_info ->> 'name'                    AS drop_stop_raw,
    m.operator_name,
    t.meta ->> 'from'                               AS meta_from
FROM ticket_ticketnew t
LEFT JOIN user_user u                 ON u.id = t.user_id
LEFT JOIN ticket_ticketmeta m         ON m.ticket_id = t.id
LEFT JOIN replica_data_townreplica ft ON ft.id = t.from_town_id
LEFT JOIN replica_data_townreplica tt ON tt.id = t.to_town_id;
