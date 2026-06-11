from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path

from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBase import ShowBase
from panda3d.core import (
    AmbientLight,
    DirectionalLight,
    LineSegs,
    TextNode,
    Vec3,
    WindowProperties,
)

ROOT = Path(__file__).resolve().parent
ASSET_DIR = ROOT / "assets" / "cs2_weapon_model_geometry"


@dataclass(frozen=True)
class WeaponSpec:
    name: str
    damage: int
    fire_delay: float
    magazine: int
    reload_time: float
    spread: float
    reward: int
    preferred_asset_tokens: tuple[str, ...]


@dataclass
class WeaponState:
    spec: WeaponSpec
    ammo: int = field(init=False)
    reserve: int = field(init=False)
    next_fire: float = 0.0
    reloading_until: float = 0.0

    def __post_init__(self) -> None:
        self.ammo = self.spec.magazine
        self.reserve = self.spec.magazine * 4


@dataclass
class Bot:
    node: object
    health: int = 100
    cooldown: float = 0.0
    target: Vec3 = field(default_factory=Vec3)


WEAPONS = [
    WeaponSpec("KV-47 Sandstorm", 35, 0.105, 30, 1.9, 0.018, 300, ("ak", "ak47", "rifle")),
    WeaponSpec("M4 Blockade", 29, 0.092, 30, 1.7, 0.014, 300, ("m4", "m4a1", "rifle")),
    WeaponSpec("Long Goose AWP", 95, 1.15, 5, 2.6, 0.004, 100, ("awp", "sniper")),
    WeaponSpec("P250 Mirage", 22, 0.22, 13, 1.25, 0.022, 300, ("p250", "pistol")),
]

SKINS = [
    ("Factory Beige", "common", 55),
    ("Blue Midline", "common", 35),
    ("Purple Tunnel", "rare", 8),
    ("Red Goose", "epic", 1.7),
    ("Golden Defuser", "legendary", 0.3),
]


class EbanoEGovno2(ShowBase):
    def __init__(self) -> None:
        super().__init__()
        self.disableMouse()
        self.setBackgroundColor(0.58, 0.72, 0.92, 1)
        self.win.setClearColorActive(True)

        self.keys: set[str] = set()
        self.mouse_locked = True
        self.velocity = Vec3(0, 0, 0)
        self.player_health = 100
        self.money = 1600
        self.cases = 1
        self.inventory: list[str] = []
        self.current_weapon = 0
        self.weapons = [WeaponState(spec) for spec in WEAPONS]
        self.bots: list[Bot] = []
        self.walls: list[tuple[float, float, float, float]] = []
        self.bomb_sites: list[Vec3] = []
        self.round_message = "Нейтрализуй ботов и собирай деньги на кейсы"
        self.last_hitmarker = 0.0
        self.round_won_awarded = False

        self.camera.setPos(0, -34, 2.0)
        self.camera.setHpr(0, 0, 0)
        self._setup_window()
        self._setup_lights()
        self._setup_input()
        self._build_map()
        self._build_crosshair()
        self.weapon_view = self.render.attachNewNode("weapon_view")
        self._equip_weapon(0)
        self._spawn_bots()
        self._setup_hud()
        self.taskMgr.add(self._update, "update")

    def _setup_window(self) -> None:
        props = WindowProperties()
        props.setTitle("EbanoE GovnO 2")
        props.setCursorHidden(True)
        props.setMouseMode(WindowProperties.M_relative)
        self.win.requestProperties(props)

    def _setup_lights(self) -> None:
        ambient = AmbientLight("ambient")
        ambient.setColor((0.42, 0.38, 0.32, 1))
        self.render.setLight(self.render.attachNewNode(ambient))
        sun = DirectionalLight("sun")
        sun.setColor((0.95, 0.88, 0.72, 1))
        sun_np = self.render.attachNewNode(sun)
        sun_np.setHpr(-35, -55, 0)
        self.render.setLight(sun_np)

    def _setup_input(self) -> None:
        for key in ["w", "a", "s", "d", "shift", "space"]:
            self.accept(key, self.keys.add, [key])
            self.accept(f"{key}-up", self.keys.discard, [key])
        self.accept("mouse1", self._shoot)
        self.accept("r", self._reload)
        self.accept("b", self._buy_case)
        self.accept("o", self._open_case)
        self.accept("f1", self._restart_round)
        self.accept("escape", self._toggle_mouse)
        for i in range(4):
            self.accept(str(i + 1), self._equip_weapon, [i])

    def _setup_hud(self) -> None:
        self.hud = OnscreenText(
            text="",
            pos=(-1.31, 0.92),
            scale=0.045,
            fg=(1, 1, 1, 1),
            align=TextNode.ALeft,
            mayChange=True,
        )
        self.message = OnscreenText(
            text=self.round_message,
            pos=(0, -0.88),
            scale=0.052,
            fg=(1, 0.88, 0.35, 1),
            align=TextNode.ACenter,
            mayChange=True,
        )

    def _build_crosshair(self) -> None:
        lines = LineSegs("crosshair")
        lines.setThickness(2)
        lines.setColor(0.85, 1, 0.85, 1)
        gap = 0.018
        size = 0.045
        for start, end in [((-size, 0, 0), (-gap, 0, 0)), ((gap, 0, 0), (size, 0, 0)), ((0, 0, -size), (0, 0, -gap)), ((0, 0, gap), (0, 0, size))]:
            lines.moveTo(*start)
            lines.drawTo(*end)
        self.aspect2d.attachNewNode(lines.create())

    def _build_map(self) -> None:
        self._box("ground", (0, 0, -0.08), (66, 74, 0.16), (0.72, 0.60, 0.43, 1))
        self._box("t_spawn", (0, -34, 0.05), (12, 8, 0.1), (0.82, 0.68, 0.45, 1))
        self.bomb_sites = [Vec3(-22, 25, 0.15), Vec3(23, 15, 0.15)]
        self._box("site_a", self.bomb_sites[0], (11, 9, 0.12), (0.75, 0.48, 0.28, 1))
        self._box("site_b", self.bomb_sites[1], (10, 10, 0.12), (0.58, 0.50, 0.38, 1))

        # Original training-map layout inspired by tactical lanes: Long, Mid, Cat and B tunnels.
        for name, pos, scale in [
            ("back_wall", (0, -39, 2.5), (68, 2, 5)), ("front_wall", (0, 38, 2.5), (68, 2, 5)),
            ("left_wall", (-34, 0, 2.5), (2, 78, 5)), ("right_wall", (34, 0, 2.5), (2, 78, 5)),
            ("mid_left", (-10, -5, 2.2), (2, 45, 4.4)), ("mid_right", (10, -7, 2.2), (2, 37, 4.4)),
            ("long_wall", (-24, -6, 2.2), (2, 45, 4.4)), ("a_ramp", (-17, 19, 1.4), (13, 2, 2.8)),
            ("b_tunnel_1", (23, -12, 2.0), (15, 2, 4)), ("b_tunnel_2", (16, 1, 2.0), (2, 24, 4)),
            ("catwalk", (-5, 14, 1.2), (16, 2, 2.4)), ("goose", (-28, 29, 1.4), (3, 7, 2.8)),
            ("xbox", (0, 2, 1.1), (5, 5, 2.2)), ("car", (-29, 10, 1.0), (5, 9, 2)),
            ("b_boxes", (26, 23, 1.1), (6, 4, 2.2)), ("doors", (0, -17, 1.7), (8, 1, 3.4)),
        ]:
            self._wall(name, pos, scale)

    def _box(self, name: str, pos: tuple[float, float, float] | Vec3, scale: tuple[float, float, float], color: tuple[float, float, float, float]):
        model = self.loader.loadModel("models/box")
        model.setName(name)
        model.reparentTo(self.render)
        model.setPos(pos)
        model.setScale(scale)
        model.setColor(color)
        return model

    def _wall(self, name: str, pos: tuple[float, float, float], scale: tuple[float, float, float]) -> None:
        self._box(name, pos, scale, (0.64 + random.random() * 0.08, 0.52, 0.35, 1))
        x, y, _ = pos
        sx, sy, _ = scale
        self.walls.append((x - sx / 2 - 0.35, x + sx / 2 + 0.35, y - sy / 2 - 0.35, y + sy / 2 + 0.35))

    def _spawn_bots(self) -> None:
        for bot in self.bots:
            bot.node.removeNode()
        self.bots.clear()
        for i, pos in enumerate([(-22, 24, 1), (22, 15, 1), (-6, 10, 1), (7, -6, 1), (26, -8, 1), (-26, -4, 1)]):
            node = self._box(f"bot_{i}", pos, (0.8, 0.8, 1.9), (0.12, 0.18, 0.24, 1))
            node.setTag("enemy", str(i))
            bot = Bot(node=node, target=Vec3(random.uniform(-28, 28), random.uniform(-30, 30), 1))
            self.bots.append(bot)

    def _equip_weapon(self, index: int) -> None:
        self.current_weapon = index
        self.weapon_view.removeNode()
        self.weapon_view = self.camera.attachNewNode("weapon_view")
        loaded = self._try_load_external_weapon(WEAPONS[index])
        if loaded is None:
            self._make_procedural_weapon(WEAPONS[index])
        self.round_message = f"Выбрано: {WEAPONS[index].name}"

    def _try_load_external_weapon(self, spec: WeaponSpec):
        if not ASSET_DIR.exists():
            return None
        candidates = []
        for path in ASSET_DIR.rglob("*"):
            if path.suffix.lower() in {".egg", ".bam", ".obj", ".gltf", ".glb"}:
                lowered = path.name.lower()
                if any(token in lowered for token in spec.preferred_asset_tokens):
                    candidates.append(path)
        for path in candidates[:5]:
            try:
                model = self.loader.loadModel(str(path))
            except Exception:  # Panda3D may not support every source format in the archive.
                continue
            model.reparentTo(self.weapon_view)
            model.setPos(0.42, 0.85, -0.34)
            model.setHpr(96, -8, 4)
            model.setScale(0.025)
            return model
        return None

    def _make_procedural_weapon(self, spec: WeaponSpec) -> None:
        base_color = (0.16, 0.16, 0.17, 1) if "AWP" not in spec.name else (0.08, 0.11, 0.10, 1)
        self._box("gun_body", (0.35, 0.82, -0.28), (0.14, 0.42, 0.08), base_color).reparentTo(self.weapon_view)
        self._box("gun_barrel", (0.35, 1.18, -0.25), (0.045, 0.46, 0.045), (0.05, 0.05, 0.055, 1)).reparentTo(self.weapon_view)
        self._box("gun_grip", (0.36, 0.58, -0.42), (0.08, 0.12, 0.25), (0.08, 0.07, 0.06, 1)).reparentTo(self.weapon_view)
        self._box("gun_mag", (0.35, 0.78, -0.43), (0.08, 0.10, 0.27), (0.10, 0.10, 0.11, 1)).reparentTo(self.weapon_view)

    def _update(self, task):
        dt = globalClock.getDt()
        now = globalClock.getFrameTime()
        self._move_player(dt)
        self._update_bots(dt, now)
        self._update_hud(now)
        return task.cont

    def _move_player(self, dt: float) -> None:
        if self.mouse_locked and self.mouseWatcherNode.hasMouse():
            md = self.win.getPointer(0)
            cx, cy = self.win.getXSize() // 2, self.win.getYSize() // 2
            dx, dy = md.getX() - cx, md.getY() - cy
            self.camera.setH(self.camera.getH() - dx * 0.12)
            self.camera.setP(max(-82, min(82, self.camera.getP() - dy * 0.12)))
            self.win.movePointer(0, cx, cy)

        speed = 10.5 if "shift" in self.keys else 7.0
        direction = Vec3(0, 0, 0)
        if "w" in self.keys: direction.y += 1
        if "s" in self.keys: direction.y -= 1
        if "a" in self.keys: direction.x -= 1
        if "d" in self.keys: direction.x += 1
        if direction.lengthSquared() > 0:
            direction.normalize()
        quat = self.camera.getQuat(self.render)
        forward = quat.getForward(); forward.z = 0; forward.normalize()
        right = quat.getRight(); right.z = 0; right.normalize()
        step = (forward * direction.y + right * direction.x) * speed * dt
        new_pos = self.camera.getPos() + step
        if not self._collides(new_pos):
            self.camera.setPos(new_pos.x, new_pos.y, self.camera.getZ())
        if "space" in self.keys and self.camera.getZ() <= 2.02:
            self.velocity.z = 6.0
        self.velocity.z -= 18 * dt
        z = max(2.0, self.camera.getZ() + self.velocity.z * dt)
        if z == 2.0:
            self.velocity.z = 0
        self.camera.setZ(z)

    def _collides(self, pos: Vec3) -> bool:
        return any(x1 < pos.x < x2 and y1 < pos.y < y2 for x1, x2, y1, y2 in self.walls)

    def _update_bots(self, dt: float, now: float) -> None:
        player = self.camera.getPos()
        for bot in list(self.bots):
            if bot.health <= 0:
                bot.node.removeNode()
                self.bots.remove(bot)
                continue
            pos = bot.node.getPos()
            to_player = player - pos
            if to_player.length() < 25 and self._has_line_of_sight(pos, player):
                bot.target = Vec3(player.x, player.y, 1)
                bot.node.lookAt(player)
                if now > bot.cooldown:
                    bot.cooldown = now + random.uniform(0.65, 1.2)
                    if random.random() < 0.56:
                        self.player_health = max(0, self.player_health - random.randint(4, 11))
                        self.round_message = "Попадание по тебе! Найди укрытие."
            elif (bot.target - pos).length() < 1.2:
                bot.target = Vec3(random.uniform(-29, 29), random.uniform(-31, 31), 1)
            move = bot.target - pos
            move.z = 0
            if move.lengthSquared() > 0:
                move.normalize()
                new_pos = pos + move * dt * 2.1
                if not self._collides(new_pos):
                    bot.node.setPos(new_pos.x, new_pos.y, pos.z)
        if self.player_health <= 0:
            self.round_message = "Раунд проигран. F1 — новый раунд."
        elif not self.bots and not self.round_won_awarded:
            self.round_won_awarded = True
            self.money += 900
            self.round_message = "Раунд выигран! +$900. F1 — новый раунд или B/O для кейсов."

    def _has_line_of_sight(self, start: Vec3, end: Vec3) -> bool:
        steps = max(2, int((end - start).length() / 1.5))
        for i in range(1, steps):
            point = start + (end - start) * (i / steps)
            if self._collides(point):
                return False
        return True

    def _shoot(self) -> None:
        if self.player_health <= 0:
            return
        now = globalClock.getFrameTime()
        weapon = self.weapons[self.current_weapon]
        if now < weapon.next_fire or now < weapon.reloading_until:
            return
        if weapon.ammo <= 0:
            self._reload()
            return
        weapon.ammo -= 1
        weapon.next_fire = now + weapon.spec.fire_delay
        self.weapon_view.setZ(-0.04)
        self.taskMgr.doMethodLater(0.05, lambda task: (self.weapon_view.setZ(0), task.done)[1], "weapon_recoil")

        origin = self.camera.getPos()
        aim = self.camera.getQuat(self.render).getForward()
        aim.x += random.uniform(-weapon.spec.spread, weapon.spec.spread)
        aim.z += random.uniform(-weapon.spec.spread, weapon.spec.spread)
        aim.normalize()
        best_bot, best_distance = None, 9999.0
        for bot in self.bots:
            to_bot = bot.node.getPos() + Vec3(0, 0, 0.8) - origin
            projection = to_bot.dot(aim)
            if projection <= 0 or projection > 80:
                continue
            miss = (to_bot - aim * projection).length()
            if miss < 0.9 and projection < best_distance and self._has_line_of_sight(origin, bot.node.getPos()):
                best_bot, best_distance = bot, projection
        if best_bot:
            best_bot.health -= weapon.spec.damage
            self.last_hitmarker = now
            if best_bot.health <= 0:
                self.money += weapon.spec.reward
                self.round_message = f"Фраг: +${weapon.spec.reward} за {weapon.spec.name}"
            else:
                self.round_message = f"Попадание: {best_bot.health} HP осталось"

    def _reload(self) -> None:
        weapon = self.weapons[self.current_weapon]
        if weapon.reserve <= 0 or weapon.ammo == weapon.spec.magazine:
            return
        need = weapon.spec.magazine - weapon.ammo
        take = min(need, weapon.reserve)
        weapon.reserve -= take
        weapon.reloading_until = globalClock.getFrameTime() + weapon.spec.reload_time
        self.taskMgr.doMethodLater(weapon.spec.reload_time, lambda task: self._finish_reload(weapon, take, task), "reload")
        self.round_message = "Перезарядка..."

    def _finish_reload(self, weapon: WeaponState, amount: int, task):
        weapon.ammo += amount
        return task.done

    def _buy_case(self) -> None:
        if self.money < 700:
            self.round_message = "Не хватает денег на кейс ($700)."
            return
        self.money -= 700
        self.cases += 1
        self.round_message = "Кейс куплен. Нажми O, чтобы открыть."

    def _open_case(self) -> None:
        if self.cases <= 0:
            self.round_message = "Кейсов нет. Нажми B, чтобы купить."
            return
        self.cases -= 1
        total = sum(weight for _, _, weight in SKINS)
        roll = random.uniform(0, total)
        upto = 0.0
        skin = SKINS[0]
        for entry in SKINS:
            upto += entry[2]
            if roll <= upto:
                skin = entry
                break
        label = f"{skin[0]} ({skin[1]})"
        self.inventory.append(label)
        self.round_message = f"Выпал скин: {label}"

    def _restart_round(self) -> None:
        self.camera.setPos(0, -34, 2.0)
        self.camera.setHpr(0, 0, 0)
        self.player_health = 100
        self.round_won_awarded = False
        for weapon in self.weapons:
            weapon.ammo = weapon.spec.magazine
            weapon.reserve = weapon.spec.magazine * 4
        self._spawn_bots()
        self.round_message = "Новый раунд начался."

    def _toggle_mouse(self) -> None:
        self.mouse_locked = not self.mouse_locked
        props = WindowProperties()
        props.setCursorHidden(self.mouse_locked)
        props.setMouseMode(WindowProperties.M_relative if self.mouse_locked else WindowProperties.M_absolute)
        self.win.requestProperties(props)

    def _update_hud(self, now: float) -> None:
        weapon = self.weapons[self.current_weapon]
        reload_text = " RELOAD" if now < weapon.reloading_until else ""
        hit = "  ✚" if now - self.last_hitmarker < 0.15 else ""
        inv = ", ".join(self.inventory[-3:]) if self.inventory else "пусто"
        self.hud.setText(
            f"EbanoE GovnO 2\n"
            f"HP: {self.player_health}   $: {self.money}   Кейсы: {self.cases}\n"
            f"Оружие: {weapon.spec.name}{reload_text}\n"
            f"Патроны: {weapon.ammo}/{weapon.reserve}   Боты: {len(self.bots)}{hit}\n"
            f"Инвентарь: {inv}\n"
            f"WASD/Mouse/ЛКМ/R/1-4/B/O/F1/Esc"
        )
        self.message.setText(self.round_message)


if __name__ == "__main__":
    game = EbanoEGovno2()
    game.run()
