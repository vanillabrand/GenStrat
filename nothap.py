from wetransferpy import WeTransfer
wt = WeTransfer()
url = wt.uploadFile('genStrat.zip')
print(url)