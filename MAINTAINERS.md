# Maintainers, and what happens if there are none

KRouter has **one maintainer** ([398894496-arch](https://github.com/398894496-arch)). That is the main risk in
adopting it, so this page says what you keep if the project stops, and how it could continue without its author.

## What you keep if KRouter stops tomorrow

- **Your memory.** It is a folder of plain Markdown pages in a place you chose. Nothing in it needs KRouter to be read,
  searched or edited: Obsidian, any editor and `grep` work on it as they do today. `scripts/uninstall.sh` removes what
  the installer added and never touches the folder.
- **Everything that runs.** The router, the MCP server and the nightly job are standard-library Python 3.9+ under the
  MIT license. There is no hosted service, no account and no server of ours to switch off; a copy you installed keeps
  working with no network at all. Model calls, when you turned them on, go to the provider you chose with your own key
  or CLI.
- **The way to check it.** CI, the release workflow, `scripts/verify_clean.sh`, the benchmarks and their registered
  rules (`bench/memory_honesty/HELDOUT.md`) are all in this repository, so a fork can release and re-measure without
  asking anyone.

## How it continues without its author

- **Anyone can pin and fork.** `KROUTER_TAG=v2.1.1` (any tag) installs that release; a fork only has to change the
  repository URL in `scripts/install.sh` and `scripts/bootstrap.py`.
- **If the repository goes quiet** (no commit, release or reply to issues for 90 days), the maintainer intends to
  either hand the repository to a contributor who asks for it in an issue, or archive it with a pointer at the fork
  most people use. Until then a long-lived fork is welcome and will be linked from the README on request.
- **Becoming a maintainer.** Two merged pull requests that change behaviour (not only docs) and one useful review of
  someone else's: ask for write access in an issue and it will be offered. Releases and the benchmark rules then
  follow [`CONTRIBUTING.md`](CONTRIBUTING.md) like everyone else's changes.

## How decisions are made

- In the open: an issue or a [discussion](https://github.com/398894496-arch/KRouter/discussions) first, then a pull
  request. A change to ranking or refusal ships with before-and-after numbers on the same run (`CONTRIBUTING.md`).
- Benchmark sets are registered before anything runs on them, and the result is reported whatever it shows
  ([`HELDOUT.md`](bench/memory_honesty/HELDOUT.md)).
- Security reports: [`SECURITY.md`](SECURITY.md).

---

# 维护者，以及没人维护时会怎样

KRouter 目前只有**一位维护者**。这是用它的最大风险，所以这一页写清楚：项目停了你还剩什么，以及没有作者时它怎么继续。

- **你的记忆还在**：它是你自己选的目录里的一堆纯 Markdown 页面，不靠 KRouter 也能读、能搜、能改。`scripts/uninstall.sh`
  只删安装脚本加的东西，从不碰这个目录。
- **能跑的都还能跑**：路由、MCP 服务、夜间任务都是只用标准库的 Python（MIT 许可）。没有托管服务、没有账号，也没有我们的服务器可以被关掉；已经装好的副本断网也照常工作。
- **验证的办法也在仓库里**：CI、发版流程、`scripts/verify_clean.sh`、评测和事先登记的规则都在这里，分叉出去也能自己发版、自己复测。
- **仓库连续 90 天没有提交、发版或回复 issue**：维护者打算把仓库交给在 issue 里提出接手的贡献者，或者归档并指向用的人最多的分叉。
- **成为维护者**：合并两个改了行为的 PR（不只是文档），再认真审过一个别人的 PR，在 issue 里提出来，就会给你写权限。
