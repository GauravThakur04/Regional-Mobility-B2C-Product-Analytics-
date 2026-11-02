-- apnibus-service-db: card taps on the conductor machine (service_app_servicebooking).
-- Customer = salted md5 of the user's mobile (same salt as the commuter DB), else the card's NFC id.
SELECT
    b.uuid::text                                               AS booking_id,
    md5(%(salt)s || coalesce(u.mobile::text, 'nfc:' || (b.meta ->> 'nfc_id'))) AS customer_key,
    md5(%(salt)s || 'nfc:' || coalesce(b.meta ->> 'nfc_id', ''))  AS card_key,
    coalesce(u.is_test_user, false)                            AS is_test_user,
    b.is_deleted, b.booking_type, b.booking_status, b.payment_status,
    b.ticket_meta ->> 'bookingSource'                          AS booking_source,
    b.ticket_meta ->> 'paymentType'                            AS payment_type,
    b.ticket_meta ->> 'concession_name'                        AS concession,
    b.ticket_meta ->> 'localStatusOfTicket'                    AS local_status,
    (b.created_at AT TIME ZONE 'Asia/Kolkata')                 AS created_at,
    to_timestamp((b.meta ->> 'timestamp')::bigint / 1000.0) AT TIME ZONE 'Asia/Kolkata' AS tapped_at,
    b.busroute_id, b.bus_number, b.operator_id,
    b.from_timetable::text AS from_timetable, b.to_timetable::text AS to_timetable,
    (b.ticket_meta ->> 'startTownSequence')::int               AS from_seq,
    (b.ticket_meta ->> 'endTownSequence')::int                 AS to_seq,
    b.seat_count, b.fare, b.paid_amount, b.card_discount, b.total_discount, b.is_free_ticket,
    (b.meta ->> 'old_balance')::numeric                        AS old_balance,
    (b.meta ->> 'new_balance')::numeric                        AS new_balance
FROM service_app_servicebooking b
LEFT JOIN user_user u ON u.uuid = b.user_id;
