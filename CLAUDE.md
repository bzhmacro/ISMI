# Git author: one, always

Every commit and every push to this repo, from any clone (local or cloud), is
authored and committed as

    Bretagne Macro <bretagnemacro@gmail.com>

Before the first commit in a clone:

    git config user.name  "Bretagne Macro"
    git config user.email bretagnemacro@gmail.com

and check `git log -1 --format='%an <%ae> / %cn <%ce>'` before pushing. No
other author, no placeholder address, no `Co-Authored-By` line. Vercel only
deploys commits by this author; anything else builds as blocked. Never
force-push to fix an author: re-author on a new branch.
