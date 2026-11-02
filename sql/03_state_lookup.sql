-- District -> state lookup built from towns that DO carry a state, used to fill towns whose
-- district JSON has a district name but no state_name. Only districts that map to exactly
-- one state are used (ambiguous district names are left unmapped).
SELECT lower(trim(district ->> 'name')) AS district_key,
       min(district ->> 'state_name')   AS state_name,
       count(DISTINCT district ->> 'state_name') AS n_states,
       count(*) AS n_towns
FROM replica_data_townreplica
WHERE district ->> 'state_name' IS NOT NULL
GROUP BY 1;
