from app.doctor.simhash import group_near_duplicates, hamming, normalize, simhash

SAMPLE = (
    "Always use pnpm as the package manager. Never run npm install directly. "
    "Run tests with pnpm test before committing any changes to the repository. "
    "Keep functions small and prefer composition over inheritance in all modules. " * 2
)


def test_normalize():
    assert normalize("  Hello\n World\t") == "helloworld"


def test_identical_text_same_hash():
    assert simhash(SAMPLE) == simhash(SAMPLE)


def test_single_word_change_is_near():
    assert hamming(simhash(SAMPLE), simhash(SAMPLE.replace("repository", "repo"))) <= 8


def test_tool_renamed_everywhere_is_near():
    assert hamming(simhash(SAMPLE), simhash(SAMPLE.replace("pnpm", "yarn"))) <= 8


def test_added_sentence_is_near():
    assert hamming(simhash(SAMPLE), simhash(SAMPLE + " Also format on save.")) <= 8


def test_unrelated_text_is_far():
    other = (
        "Documentation is generated with mkdocs and published on every tagged "
        "release. Contributors should preview changes locally before pushing. " * 2
    )
    assert hamming(simhash(SAMPLE), simhash(other)) > 20


def test_grouping_pairs_near_duplicates():
    near = SAMPLE.replace("repository", "repo")
    other = (
        "Deploy the frontend to Vercel and the API to Fly.io. Rollbacks are "
        "triggered from the dashboard when error rates exceed one percent. " * 2
    )
    one_more = (
        "The database schema lives in prisma/schema.prisma. Apply migrations "
        "with prisma migrate deploy on every production pipeline stage. " * 2
    )
    fps = [simhash(t) for t in [SAMPLE, near, other, one_more]]
    groups = group_near_duplicates(fps)
    assert len(groups) == 1
    assert sorted(groups[0]) == [0, 1]


def test_grouping_transitive_chain():
    a = SAMPLE
    b = SAMPLE.replace("repository", "repo")
    c = b.replace("modules", "components")
    fps = [simhash(a), simhash(b), simhash(c), simhash("totally unrelated words here " * 10)]
    groups = group_near_duplicates(fps)
    flat = sorted(idx for g in groups for idx in g)
    assert 0 in flat and 1 in flat and 2 in flat
    assert 3 not in flat
