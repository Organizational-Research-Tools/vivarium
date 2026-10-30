import pandas as pd
x=pd.read_csv('records.csv')
for p in ['p_2YHYS3GPHP','p_2YHYS3GPHM','p_2YHYS3GPHA','p_2YHYS3GPHJ','p_GJ5SWEGMPT','p_GJ5SWEGMP4','p_H6M64FVH6V']:
 g=x[x.prototype_id==p]
 print('\n',p)
 print(g.groupby(['project','test','kind','measured_by']).value.agg(['mean','count']).to_string())
 print('recipe',g.iloc[0,11:].to_dict() if len(g) else '')