import sqlite3, glob, os

for f in glob.glob(os.path.expandvars(r"%LOCALAPPDATA%\PMO HUB Files\db\*.db")):
    print("===", f)
    con = sqlite3.connect("file:" + f + "?mode=ro", uri=True)
    for (name,) in con.execute("select name from sqlite_master where type='table'"):
        try:
            n = con.execute('select count(*) from "%s"' % name).fetchone()[0]
        except Exception as e:
            n = "err %s" % e
        print("  table", name, n)
        try:
            for row in con.execute('select * from "%s" limit 3' % name):
                print("     ", str(row)[:400])
        except Exception as e:
            print("     ", e)
    con.close()
