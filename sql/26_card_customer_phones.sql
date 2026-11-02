-- apnibus-service-db: phone number for each registered card user (same customer_key as 20/24_*.sql).
-- Output stays in data/ (git-ignored); used only for the dashboard's Customer list.
SELECT md5(%(salt)s || u.mobile::text) AS customer_key, u.mobile::text AS phone
FROM user_user u
WHERE NOT u.is_deleted AND u.mobile IS NOT NULL;
