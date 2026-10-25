import os

from app.scan.repos import find_git_repos


def make_repo(base, name, extra_dirs=None):
    repo = base / name
    (repo / ".git" / "refs" / "heads").mkdir(parents=True)
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (repo / "README.md").write_text(f"# {name}\n")
    for d in extra_dirs or []:
        (repo / d).mkdir(parents=True, exist_ok=True)
    return repo


def test_finds_nested_repos(tmp_path):
    make_repo(tmp_path, "alpha")
    make_repo(tmp_path / "group", "beta")
    repos = find_git_repos(tmp_path)
    names = {r.name for r in repos}
    assert names == {"alpha", "beta"}


def test_skips_node_modules(tmp_path):
    make_repo(tmp_path, "alpha")
    make_repo(tmp_path / "node_modules", "hidden-pkg")
    repos = find_git_repos(tmp_path)
    assert {r.name for r in repos} == {"alpha"}


def test_does_not_descend_into_repo(tmp_path):
    repo = make_repo(tmp_path, "outer")
    make_repo(repo / "vendor", "inner")  # nested repo inside found repo
    repos = find_git_repos(tmp_path)
    assert {r.name for r in repos} == {"outer"}


def test_root_itself_is_repo(tmp_path):
    (tmp_path / ".git").mkdir()
    repos = find_git_repos(tmp_path)
    assert [os.path.basename(r.path) for r in repos] == [os.path.basename(tmp_path)]


def test_max_depth(tmp_path):
    deep = tmp_path
    for i in range(6):
        deep = deep / f"d{i}"
    deep.mkdir(parents=True)
    make_repo(deep.parent, "toodeep")  # sits 6 levels below tmp_path
    repos = find_git_repos(tmp_path, max_depth=2)
    assert {r.name for r in repos} == set()  # too deep to reach
    repos = find_git_repos(tmp_path, max_depth=10)
    assert "toodeep" in {r.name for r in repos}


def test_last_activity_present(tmp_path):
    make_repo(tmp_path, "alpha")
    repos = find_git_repos(tmp_path)
    # synthetic repo has no commits; fallback should still yield some mtime
    assert repos[0].last_activity is not None
