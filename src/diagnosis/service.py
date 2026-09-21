from pathlib import Path
import pandas as pd

FIELDS = ['position_state','chip_state','control_state','activity_state','capital_behavior_state',
    'capital_pressure_state','sentiment_state','market_regime_state','sentiment_direction','sentiment_intensity',
    'media_mentions_1d','negative_ratio','event_type','event_age','evidence_grade','sentiment_price_relation',
    'main_conflict','review_conditions','previous_pulse','current_pulse','pulse_changed','pulse_confidence',
    'pulse_reasons','trigger_reasons','body_state','industry_state','diagnosis_date']


def load_diagnoses(root, codes):
    result=pd.DataFrame({'code':codes})
    for field in FIELDS:
        result[field]='待诊'
    path=Path(root)/'data/pulse_watchlist.csv'
    if not path.exists():
        return result
    try:
        pulse=pd.read_csv(path,dtype={'code':str}).set_index('code')
        for i,row in result.iterrows():
            if row.code not in pulse.index:
                continue
            p=pulse.loc[row.code]
            for field in FIELDS:
                if field in p and pd.notna(p[field]):
                    result.at[i,field]=str(p[field])
            result.at[i,'diagnosis_date']=str(p.get('trade_date','待诊'))
    except (ValueError,KeyError,OSError):
        pass
    return result
