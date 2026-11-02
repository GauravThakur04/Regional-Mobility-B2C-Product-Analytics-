-- Green Card (coupon_userpass) purchases, one row per pass record.
SELECT
    p.id                                             AS pass_row_id,
    md5(%(salt)s || coalesce(u.contact::text, 'uid:' || p.user_id::text)) AS customer_key,
    coalesce(u.is_test_user, false)                  AS is_test_user,
    p.pass_id,
    p.status,
    p.is_paid,
    p.refund_status,
    p.is_deleted,
    p.payable_amount,
    (p.created_at AT TIME ZONE 'Asia/Kolkata')::date AS purchase_date
FROM coupon_userpass p
LEFT JOIN user_user u ON u.id = p.user_id;
