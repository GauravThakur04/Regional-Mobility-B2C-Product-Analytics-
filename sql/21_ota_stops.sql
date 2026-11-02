-- Route stop lists: ota_service (one row per departure, lists its bus_route_ids) → ota_service_stop.
SELECT r.route_id, s.id::text AS service_id, s.operator_name, s.departure_time, s.is_deleted AS svc_deleted,
       ss.order_index, ss.town_alias, ss.alias_en, ss.state, ss.latitude, ss.longitude, ss.is_deleted AS stop_deleted
FROM ota_service s
CROSS JOIN LATERAL jsonb_array_elements_text(s.bus_route_ids) r(route_id)
JOIN ota_service_stop ss ON ss.service_id = s.id
WHERE jsonb_typeof(s.bus_route_ids) = 'array';
