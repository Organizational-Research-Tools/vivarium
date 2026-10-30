import pandas as pd
x=pd.read_csv('records.csv')
# summarize all new crossover measurements
ids=['p_RTT858W8T1','p_RTT858W8T3','p_RTT858W8T5','p_RTT858W8T7','p_RTT858W8T9','p_RTT858W8TB','p_RTT858W8TD','p_RTT858W8TF','p_ZG7GNCT5AT','p_ZG7GNCT5AW','p_ZG7GNCT5AY','p_ZG7GNCT5B0']
for p in ids:
 d=x[x.prototype_id==p]
 print(p, d[d.kind=='exploratory'][['instrument','test','value']].to_dict('records'))
