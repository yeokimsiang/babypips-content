import re,glob,os,sys
root=sys.argv[1];B="https://www.babypips.com/learn/forex/"
os.makedirs(f"{root}/notes",exist_ok=True)
idx=["# BabyPips School of Pipsology: Index and Study Notes","",
"A map of every grade, chapter and lesson in the [BabyPips School of Pipsology](https://www.babypips.com/learn/forex), with my own condensed study notes for each lesson. Notes are original summaries, not copies of the course text; follow the links for the full lessons.",""]
tot=0;slugs=[]
for f in sorted(glob.glob(f"{root}/src/*.md")):
    name=os.path.basename(f);out=[];
    for line in open(f):
        m=re.match(r"^(#+) (.+?) \{(.+?)\}\s*$",line)
        if not m: out.append(line);continue
        h,t,s=m.groups();lvl=len(h)
        if lvl==1:
            out.append(f"# {t}\n\n[Back to index](../README.md) · [Grade on BabyPips]({B}{s})\n");idx.append(f"## [{t}](notes/{name})")
        elif lvl==2:
            out.append(f"## {t}\n");idx.append(f"\n**{t}**\n")
        else:
            tot+=1;slugs.append(s);anchor=re.sub(r"[^a-z0-9 -]","",t.lower()).replace(" ","-")
            out.append(f"### [{t}]({B}{s})\n");idx.append(f"- [{t}](notes/{name}#{anchor})")
    open(f"{root}/notes/{name}","w").write("".join(out))
idx+=["",f"_{tot} lessons across 11 grades._",""]
open(f"{root}/README.md","w").write("\n".join(idx))
open("/home/claude/tools/slugs.txt","w").write(",".join(slugs))
print(tot,len(set(slugs)))
