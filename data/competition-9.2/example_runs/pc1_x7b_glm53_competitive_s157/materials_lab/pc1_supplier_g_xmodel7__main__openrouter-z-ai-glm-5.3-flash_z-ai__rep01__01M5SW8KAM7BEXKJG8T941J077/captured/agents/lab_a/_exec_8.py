import pandas as pd
df = pd.read_csv('records.csv')
w = df[(df.prototype_id=='p_MWBXGZXWA5')&(df.instrument=='water')]
print(w[['record_id','value','measured_by','kind' if 'kind' in df.columns else 'value']].to_string())
print('water means by set:'); print(w.groupby('measured_by').value.agg(['count','mean']))
s = df[(df.prototype_id=='p_MWBXGZXWA5')&(df.instrument=='strength')]
print(s.groupby('measured_by').value.agg(['count','mean']))
print(df.columns.tolist())
# any QP-9470/2236/2347/6820 records at all?
for p in ['QP-9470','QP-2236','QP-2347','QP-6820','QP-5066']:
    sub = df[df.project_id==p]
    print(p, len(sub), sub.instrument.value_counts().to_dict() if len(sub) else '')