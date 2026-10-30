import pandas as pd
df = pd.read_csv('records.csv')
sel = df[df.record_id.str.startswith(('r_AQ0YMATTK','r_WR3QE2QZ'))]
print(sel[['record_id','prototype_id','instrument','value','measured_by']].to_string())
print(len(sel))