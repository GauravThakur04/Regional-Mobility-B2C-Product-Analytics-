-- ab_commuter: phone number for each customer of our-bus paid bookings (same customer_key as 06_our_buses_paid.sql).
-- Output stays in data/ (git-ignored); used only for the dashboard's Customer list.
SELECT DISTINCT md5(%(salt)s || u.contact::text) AS customer_key, u.contact::text AS phone
FROM ticket_ticketnew t
JOIN user_user u ON u.id = t.user_id
WHERE t.source = 1 AND t.is_paid AND u.contact IS NOT NULL;
