-- apnibus-service-db: one row per registered card user (including people who never tapped).
-- customer_key uses the same salted md5 of the mobile as 20_card_bookings.sql; the mobile itself never leaves the DB.
SELECT
    md5(%(salt)s || u.mobile::text)                         AS customer_key,
    u.language,
    (u.created_at AT TIME ZONE 'Asia/Kolkata')::date       AS signed_up,
    (u.card_id IS NOT NULL)                                AS has_card,
    (u.card_active_datetime AT TIME ZONE 'Asia/Kolkata')::date AS card_activated,
    w.balance                                              AS wallet_balance,
    (w.last_recharge_at AT TIME ZONE 'Asia/Kolkata')::date AS last_recharge
FROM user_user u
LEFT JOIN user_wallet w ON w.user_id = u.uuid AND NOT w.is_deleted
WHERE NOT u.is_deleted AND NOT coalesce(u.is_test_user, false) AND u.mobile IS NOT NULL;
