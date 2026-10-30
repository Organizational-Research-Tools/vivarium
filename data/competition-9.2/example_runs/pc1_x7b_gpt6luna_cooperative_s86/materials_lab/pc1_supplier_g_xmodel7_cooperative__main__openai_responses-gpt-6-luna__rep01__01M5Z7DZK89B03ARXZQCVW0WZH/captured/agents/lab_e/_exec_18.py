import pandas as pd
x=pd.read_csv('records.csv')
cols=list(x.columns[11:])
for pid in ['p_QDC2E5V23W','p_QDC2E5V23Y','p_QDC2E5V240','p_P8NCNQ5S6C','p_BY88JQM72B','p_Y9Y4J1ZWSF','p_0Z7742JGRX','p_JP6EPY2552','p_ATC1TY4VCY','p_02AJ2E0D53']:
 z=x[x.prototype_id.eq(pid)]
 if len(z): print(pid,z.project.iloc[0],dict(zip(cols,z.iloc[0][cols])))
