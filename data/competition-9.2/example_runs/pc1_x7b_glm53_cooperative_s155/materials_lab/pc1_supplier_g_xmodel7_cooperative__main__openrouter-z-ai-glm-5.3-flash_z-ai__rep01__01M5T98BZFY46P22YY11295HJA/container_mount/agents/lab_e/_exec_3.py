import pandas as pd
df = pd.read_csv('records.csv')
recs = ['r_F5YJWBCWK0','r_F5YJWBCWK1','r_F5YJWBCWK2','r_F5YJWBCWK3','r_F5YJWBCWK4','r_F5YJWBCWK5',
'r_F6QRHYNC1K','r_F6QRHYNC1M','r_F6QRHYNC1N','r_F6QRHYNC1P','r_F6QRHYNC1Q','r_F6QRHYNC1R',
'r_1DT48DXK1X','r_1DT48DXK1Y','r_1DT48DXK1Z','r_1DT48DXK20','r_1DT48DXK21','r_1DT48DXK22',
'r_BWM5GYHMKF','r_BWM5GYHMKG','r_BWM5GYHMKH','r_BWM5GYHMKJ','r_BWM5GYHMKK','r_BWM5GYHMKM']
sub = df[df['record_id'].isin(recs)]
print(sub[['record_id','project_id','prototype_id','test','specimen','value','measured_by']].to_string())
