# app/forecast_engine.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
import calendar

MONTHS_RO = ['Ian','Feb','Mar','Apr','Mai','Iun','Iul','Aug','Sep','Oct','Nov','Dec']
SAFETY_DAYS = 30

URGENCY_THRESHOLDS = {
    'Ceai':      {'critic': 150, 'atentie': 210},
    'Ciocolata': {'critic': 60,  'atentie': 90},
    'Altele':    {'critic': 60,  'atentie': 90},
}


@dataclass
class SkuResult:
    sku: str
    cod_produs: str
    descriere: str
    furnizor: str
    gama: str
    tip_produs: str

    stoc_fizic_ro: float = 0.0
    stoc_fizic_hu: float = 0.0
    in_tranzit_ro: float = 0.0
    in_tranzit_hu: float = 0.0

    stoc_net_ro: float = 0.0
    stoc_net_hu: float = 0.0

    avg_monthly_ro: float = 0.0
    avg_monthly_hu: float = 0.0

    zile_stoc_fizic_ro: float | None = None
    zile_stoc_fizic_hu: float | None = None
    zile_stoc_net_ro: float | None = None
    zile_stoc_net_hu: float | None = None
    zile_stoc_cu_tranzit_ro: float | None = None
    zile_stoc_cu_tranzit_hu: float | None = None

    sugestie_ro: int = 0
    sugestie_hu: int = 0

    urgenta_ro: str = 'fara_miscare'
    urgenta_hu: str = 'fara_miscare'

    seasonality_ro: list = field(default_factory=list)
    seasonality_hu: list = field(default_factory=list)

    # comenzi active vizibile pe rând
    comenzi_active: list = field(default_factory=list)


class ForecastEngine:

    def seasonality_index(self, monthly_sales: dict, target_month: int) -> float:
        """Index sezonalitate pentru luna target față de media anuală.
        monthly_sales: {1..12: qty_medie}. Returnează 1.0 dacă date lipsă."""
        values = [v for v in monthly_sales.values() if v > 0]
        if not values:
            return 1.0
        annual_avg = sum(values) / len(values)
        if annual_avg == 0:
            return 1.0
        return monthly_sales.get(target_month, annual_avg) / annual_avg

    def coverage_demand(self, daily_rate: float, lead_days: int, season_idx: float) -> float:
        """Cerere totală de la azi până la azi + lead_days + SAFETY_DAYS.
        Prorată pentru luni parțiale, ajustată cu sezonalitate."""
        if daily_rate <= 0:
            return 0.0
        total_days = lead_days + SAFETY_DAYS
        today = date.today()
        demand = 0.0
        current = today
        remaining = total_days
        while remaining > 0:
            days_in_month = calendar.monthrange(current.year, current.month)[1]
            days_left_in_month = days_in_month - current.day + 1
            days_this_chunk = min(remaining, days_left_in_month)
            demand += daily_rate * days_this_chunk * season_idx
            remaining -= days_this_chunk
            if remaining > 0:
                if current.month == 12:
                    current = date(current.year + 1, 1, 1)
                else:
                    current = date(current.year, current.month + 1, 1)
        return demand

    def apply_yoy_trend(self, current_avg: float, prev_avg: float) -> float:
        """Factor de corecție YoY. Dacă prev=0 returnează 1.0 (fără corecție)."""
        if prev_avg <= 0 or current_avg <= 0:
            return 1.0
        return current_avg / prev_avg

    def urgency(self, zile: float | None, tip_produs: str) -> str:
        if zile is None:
            return 'fara_miscare'
        thresholds = URGENCY_THRESHOLDS.get(tip_produs, URGENCY_THRESHOLDS['Altele'])
        if zile < thresholds['critic']:
            return 'critic'
        if zile < thresholds['atentie']:
            return 'atentie'
        return 'ok'

    def _zile(self, stoc: float, daily_rate: float) -> float | None:
        if daily_rate <= 0:
            return None
        return round(stoc / daily_rate, 1)

    def _build_seasonality(self, monthly_avg: dict) -> list:
        """Returnează listă de 12 dict-uri {label, avg, idx} pentru afișare."""
        annual_vals = [monthly_avg.get(m, 0) for m in range(1, 13)]
        annual_mean = sum(annual_vals) / 12 if sum(annual_vals) > 0 else 1
        return [
            {
                'label': MONTHS_RO[m - 1],
                'avg': round(monthly_avg.get(m, 0), 1),
                'idx': round(monthly_avg.get(m, 0) / annual_mean, 2) if annual_mean else 1.0,
            }
            for m in range(1, 13)
        ]

    def compute_sku(
        self,
        sku: str,
        cod_produs: str,
        descriere: str,
        furnizor: str,
        gama: str,
        tip_produs: str,
        stoc_fizic_ro: float,
        stoc_fizic_hu: float,
        avg_ro: dict,        # {1..12: qty_medie} ultimele 12 luni
        avg_hu: dict,
        avg_ro_prev: dict,   # {1..12: qty_medie} anul anterior (pentru YoY)
        avg_hu_prev: dict,
        lead_days: int,
        in_transit_ro: float,
        in_transit_hu: float,
        comenzi_active: list,
    ) -> SkuResult:
        r = SkuResult(
            sku=sku, cod_produs=cod_produs, descriere=descriere,
            furnizor=furnizor, gama=gama, tip_produs=tip_produs,
            stoc_fizic_ro=stoc_fizic_ro, stoc_fizic_hu=stoc_fizic_hu,
            in_tranzit_ro=in_transit_ro, in_tranzit_hu=in_transit_hu,
            comenzi_active=comenzi_active,
        )

        # Medii lunare (ultimele 12 luni)
        r.avg_monthly_ro = sum(avg_ro.values()) / 12 if avg_ro else 0.0
        r.avg_monthly_hu = sum(avg_hu.values()) / 12 if avg_hu else 0.0

        # YoY trend
        prev_avg_ro = sum(avg_ro_prev.values()) / 12 if avg_ro_prev else 0.0
        prev_avg_hu = sum(avg_hu_prev.values()) / 12 if avg_hu_prev else 0.0
        trend_ro = self.apply_yoy_trend(r.avg_monthly_ro, prev_avg_ro)
        trend_hu = self.apply_yoy_trend(r.avg_monthly_hu, prev_avg_hu)

        daily_ro = (r.avg_monthly_ro * trend_ro) / 30.0
        daily_hu = (r.avg_monthly_hu * trend_hu) / 30.0

        # Sezonalitate luna curentă
        today_month = date.today().month
        season_ro = self.seasonality_index(avg_ro, today_month)
        season_hu = self.seasonality_index(avg_hu, today_month)

        # Stoc net (după deducere comenzi active)
        r.stoc_net_ro = max(0.0, stoc_fizic_ro - in_transit_ro)
        r.stoc_net_hu = max(0.0, stoc_fizic_hu - in_transit_hu)

        # Zile stoc
        r.zile_stoc_fizic_ro = self._zile(stoc_fizic_ro, daily_ro)
        r.zile_stoc_fizic_hu = self._zile(stoc_fizic_hu, daily_hu)
        r.zile_stoc_net_ro   = self._zile(r.stoc_net_ro, daily_ro)
        r.zile_stoc_net_hu   = self._zile(r.stoc_net_hu, daily_hu)
        r.zile_stoc_cu_tranzit_ro = self._zile(stoc_fizic_ro + in_transit_ro, daily_ro)
        r.zile_stoc_cu_tranzit_hu = self._zile(stoc_fizic_hu + in_transit_hu, daily_hu)

        # Necesar acoperire
        necesar_ro = self.coverage_demand(daily_ro, lead_days, season_ro)
        necesar_hu = self.coverage_demand(daily_hu, lead_days, season_hu)

        # Sugestii (niciodată negative)
        r.sugestie_ro = max(0, round(necesar_ro - r.stoc_net_ro))
        r.sugestie_hu = max(0, round(necesar_hu - r.stoc_net_hu))

        # Urgențe pe zile_stoc_net
        r.urgenta_ro = self.urgency(r.zile_stoc_net_ro, tip_produs)
        r.urgenta_hu = self.urgency(r.zile_stoc_net_hu, tip_produs)

        # Sezonalitate pentru afișare
        r.seasonality_ro = self._build_seasonality(avg_ro)
        r.seasonality_hu = self._build_seasonality(avg_hu)

        return r
