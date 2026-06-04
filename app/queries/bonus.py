from db import query


def bonus_team():
    return query("""
        SELECT employee_id, nume, rol, activ,
            bonus_target_lunar_ron, bonus_target_trim_ron, observatii
        FROM echipa WHERE activ = 1
        ORDER BY bonus_target_lunar_ron DESC
    """)


