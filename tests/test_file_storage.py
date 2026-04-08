import logging

import pytest

from sondera import Adjudicated, Agent, Event, Thought, Trajectory, TrajectoryStatus
from sondera.harness.trajectory.abc import AdjudicatedStep, AdjudicatedTrajectory
from sondera.harness.trajectory.file_storage import FileTrajectoryStorage

INVALID_PATH_COMPONENTS = [
    pytest.param("", id="empty"),
    pytest.param(".", id="dot"),
    pytest.param("..", id="dotdot"),
    pytest.param("../outside", id="posix-traversal"),
    pytest.param("nested/path", id="posix-nested"),
    pytest.param(r"nested\path", id="windows-nested"),
    pytest.param("/abs/path", id="posix-absolute"),
    pytest.param(r"C:\temp\file", id="windows-absolute"),
]

HOSTILE_COMPONENT = "../outside"


def _trajectory(
    *, agent_id: str = "agent-1", trajectory_id: str = "traj-1"
) -> Trajectory:
    return Trajectory(
        name=trajectory_id,
        agent=agent_id,
        status=TrajectoryStatus.Running,
    )


def _adjudicated_trajectory(
    *, agent_id: str = "agent-1", trajectory_id: str = "traj-1"
) -> AdjudicatedTrajectory:
    return AdjudicatedTrajectory(
        id=trajectory_id,
        agent=agent_id,
        status=TrajectoryStatus.Running,
        steps=[],
    )


def _step(
    *, agent_id: str = "agent-1", trajectory_id: str = "traj-1"
) -> AdjudicatedStep:
    event = Event(
        agent=Agent(id=agent_id, provider="test"),
        trajectory_id=trajectory_id,
        event=Thought("persist step"),
    )
    return AdjudicatedStep(event=event, adjudication=Adjudicated.allow())


class TestFileTrajectoryStoragePathSafety:
    @pytest.mark.asyncio
    async def test_round_trips_safe_ids(self, tmp_path):
        storage = FileTrajectoryStorage(tmp_path)
        storage.init_trajectory(_trajectory())

        trajectories, next_token = await storage.list_trajectories("agent-1")
        loaded = await storage.get_trajectory("traj-1")

        assert next_token == ""
        assert [traj.name for traj in trajectories] == ["traj-1"]
        assert loaded is not None
        assert loaded.agent == "agent-1"
        assert loaded.id == "traj-1"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("api_name", "call"),
        [
            pytest.param(
                "list_trajectories",
                lambda storage, agent_id: storage.list_trajectories(agent_id),
                id="list_trajectories",
            ),
            pytest.param(
                "analyze_trajectories",
                lambda storage, agent_id: storage.analyze_trajectories(
                    agent_id, analytics=["trajectory_count"]
                ),
                id="analyze_trajectories",
            ),
        ],
    )
    @pytest.mark.parametrize("invalid_agent_id", INVALID_PATH_COMPONENTS)
    async def test_agent_id_path_apis_reject_invalid_components(
        self, tmp_path, api_name, call, invalid_agent_id
    ):
        storage = FileTrajectoryStorage(tmp_path)

        with pytest.raises(ValueError, match="agent_id"):
            await call(storage, invalid_agent_id)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("invalid_trajectory_id", INVALID_PATH_COMPONENTS)
    async def test_get_trajectory_rejects_invalid_components(
        self, tmp_path, invalid_trajectory_id
    ):
        storage = FileTrajectoryStorage(tmp_path)

        with pytest.raises(ValueError, match="trajectory_id"):
            await storage.get_trajectory(invalid_trajectory_id)

    @pytest.mark.parametrize(
        ("call", "field_name"),
        [
            pytest.param(
                lambda storage: storage.init_trajectory(
                    _trajectory(agent_id=HOSTILE_COMPONENT)
                ),
                "agent_id",
                id="init_trajectory-agent_id",
            ),
            pytest.param(
                lambda storage: storage.init_trajectory(
                    _trajectory(trajectory_id=HOSTILE_COMPONENT)
                ),
                "trajectory_id",
                id="init_trajectory-trajectory_id",
            ),
            pytest.param(
                lambda storage: storage.save_trajectory(
                    _adjudicated_trajectory(agent_id=HOSTILE_COMPONENT)
                ),
                "agent_id",
                id="save_trajectory-agent_id",
            ),
            pytest.param(
                lambda storage: storage.save_trajectory(
                    _adjudicated_trajectory(trajectory_id=HOSTILE_COMPONENT)
                ),
                "trajectory_id",
                id="save_trajectory-trajectory_id",
            ),
            pytest.param(
                lambda storage: storage.append_step(
                    HOSTILE_COMPONENT, "traj-1", _step()
                ),
                "agent_id",
                id="append_step-agent_id",
            ),
            pytest.param(
                lambda storage: storage.append_step(
                    "agent-1", HOSTILE_COMPONENT, _step()
                ),
                "trajectory_id",
                id="append_step-trajectory_id",
            ),
            pytest.param(
                lambda storage: storage.finalize_trajectory(
                    HOSTILE_COMPONENT, "traj-1"
                ),
                "agent_id",
                id="finalize_trajectory-agent_id",
            ),
            pytest.param(
                lambda storage: storage.finalize_trajectory(
                    "agent-1", HOSTILE_COMPONENT
                ),
                "trajectory_id",
                id="finalize_trajectory-trajectory_id",
            ),
        ],
    )
    def test_write_apis_reject_hostile_ids_consistently(
        self, tmp_path, call, field_name
    ):
        storage = FileTrajectoryStorage(tmp_path)

        with pytest.raises(
            ValueError, match=rf"{field_name} must be a single path component"
        ):
            call(storage)

    @pytest.mark.asyncio
    async def test_get_trajectory_skips_symlink_escape_and_finds_valid_file(
        self, tmp_path, caplog, monkeypatch
    ):
        storage_root = tmp_path / "trajectories"
        outside_root = tmp_path / "outside"
        bad_agent_dir = storage_root / "bad-agent"
        good_agent_dir = storage_root / "good-agent"

        storage_root.mkdir()
        outside_root.mkdir()
        good_agent_dir.mkdir()

        try:
            bad_agent_dir.symlink_to(outside_root, target_is_directory=True)
        except (NotImplementedError, OSError):
            pytest.skip("symlinks are not supported in this test environment")

        storage = FileTrajectoryStorage(storage_root)
        storage.init_trajectory(_trajectory(agent_id="good-agent"))

        root_type = storage._root.__class__
        original_iterdir = root_type.iterdir

        def fake_iterdir(self):
            if self == storage._root:
                return iter([bad_agent_dir, good_agent_dir])
            return original_iterdir(self)

        monkeypatch.setattr(root_type, "iterdir", fake_iterdir)

        with caplog.at_level(
            logging.WARNING, logger="sondera.harness.trajectory.file_storage"
        ):
            loaded = await storage.get_trajectory("traj-1")

        assert loaded is not None
        assert loaded.agent == "good-agent"
        assert loaded.id == "traj-1"
        assert "Skipping trajectory path outside storage root" in caplog.text

    def test_init_trajectory_rejects_symlink_escape_outside_root(self, tmp_path):
        storage_root = tmp_path / "trajectories"
        outside_root = tmp_path / "outside"
        storage_root.mkdir()
        outside_root.mkdir()

        try:
            (storage_root / "agent-1").symlink_to(
                outside_root, target_is_directory=True
            )
        except (NotImplementedError, OSError):
            pytest.skip("symlinks are not supported in this test environment")

        storage = FileTrajectoryStorage(storage_root)

        with pytest.raises(ValueError, match="escapes trajectory root"):
            storage.init_trajectory(_trajectory())
