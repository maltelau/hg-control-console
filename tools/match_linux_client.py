#!/usr/bin/env python3
"""Match HGCC hook landmarks in the NWN 1.69 Linux client.

The Linux client is a 32-bit, non-PIE ELF build. Absolute immediates and
RTTI/string references are stable enough to use as validation anchors before a
Linux hook module enables any hard-coded call targets.
"""

from __future__ import annotations

import argparse
import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


DEFAULT_LINUX_CLIENT = Path(
    r"H:\My Drive\Codex Projects\NWN Linux\English_linuxclient169_xp2.tar"
    r"\English_linuxclient_xp2\nwmain"
)
DEFAULT_DIAMOND_EXE = Path(
    r"H:\My Drive\Codex Projects\NWN EE Bridge\NWN Diamond\nwmain.exe"
)


def hex32(value: Optional[int]) -> Optional[str]:
    if value is None:
        return None
    return f"0x{value:08X}"


def u32(value: int) -> bytes:
    return struct.pack("<I", value)


@dataclass(frozen=True)
class Section:
    name: str
    va: int
    offset: int
    size: int
    raw_size: int
    section_type: int = 0

    @property
    def end_va(self) -> int:
        return self.va + self.size

    @property
    def end_offset(self) -> int:
        return self.offset + self.raw_size


@dataclass
class BinaryImage:
    path: Path
    kind: str
    bits: int
    entry: int
    image_base: int
    data: bytes
    sections: list[Section]

    def section(self, name: str) -> Optional[Section]:
        for section in self.sections:
            if section.name == name:
                return section
        return None

    def va_to_offset(self, va: int) -> Optional[int]:
        for section in self.sections:
            if section.va <= va < section.va + section.raw_size:
                return section.offset + (va - section.va)
            if section.raw_size == 0 and section.va <= va < section.end_va:
                return None
        return None

    def offset_to_va(self, offset: int) -> Optional[int]:
        for section in self.sections:
            if section.offset <= offset < section.end_offset:
                return section.va + (offset - section.offset)
        return None

    def read_va(self, va: int, size: int) -> bytes:
        offset = self.va_to_offset(va)
        if offset is None:
            return b""
        return self.data[offset : offset + size]

    def find_bytes(self, needle: bytes, section_names: Optional[Iterable[str]] = None) -> list[int]:
        names = set(section_names) if section_names is not None else None
        offsets: list[int] = []
        for section in self.sections:
            if names is not None and section.name not in names:
                continue
            if section.raw_size <= 0:
                continue
            blob = self.data[section.offset : section.offset + section.raw_size]
            start = 0
            while True:
                hit = blob.find(needle, start)
                if hit < 0:
                    break
                offsets.append(section.offset + hit)
                start = hit + 1
        return offsets


def parse_elf32(path: Path, data: bytes) -> BinaryImage:
    if data[:4] != b"\x7fELF" or data[4] != 1 or data[5] != 1:
        raise ValueError(f"{path} is not a little-endian ELF32 file")

    (
        _ident,
        _etype,
        _machine,
        _version,
        entry,
        _phoff,
        shoff,
        _flags,
        _ehsize,
        _phentsize,
        _phnum,
        shentsize,
        shnum,
        shstrndx,
    ) = struct.unpack_from("<16sHHIIIIIHHHHHH", data, 0)

    raw_sections = []
    for index in range(shnum):
        off = shoff + index * shentsize
        raw_sections.append(struct.unpack_from("<IIIIIIIIII", data, off))

    shstr = raw_sections[shstrndx]
    shstr_data = data[shstr[4] : shstr[4] + shstr[5]]

    def section_name(name_off: int) -> str:
        end = shstr_data.find(b"\0", name_off)
        if end < 0:
            end = len(shstr_data)
        return shstr_data[name_off:end].decode("ascii", errors="replace")

    sections: list[Section] = []
    for raw in raw_sections:
        name_off, sh_type, _flags, addr, offset, size, *_rest = raw
        raw_size = 0 if sh_type == 8 else size
        sections.append(Section(section_name(name_off), addr, offset, size, raw_size, sh_type))

    return BinaryImage(path, "ELF", 32, entry, 0, data, sections)


def parse_pe32(path: Path, data: bytes) -> BinaryImage:
    if data[:2] != b"MZ":
        raise ValueError(f"{path} is not a PE file")
    pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_off : pe_off + 4] != b"PE\0\0":
        raise ValueError(f"{path} has an invalid PE header")

    coff_off = pe_off + 4
    section_count = struct.unpack_from("<H", data, coff_off + 2)[0]
    optional_size = struct.unpack_from("<H", data, coff_off + 16)[0]
    optional_off = coff_off + 20
    magic = struct.unpack_from("<H", data, optional_off)[0]
    if magic != 0x10B:
        raise ValueError(f"{path} is not a PE32 image")

    entry_rva = struct.unpack_from("<I", data, optional_off + 16)[0]
    image_base = struct.unpack_from("<I", data, optional_off + 28)[0]
    section_off = optional_off + optional_size

    sections: list[Section] = []
    for index in range(section_count):
        off = section_off + index * 40
        raw_name = data[off : off + 8].split(b"\0", 1)[0]
        name = raw_name.decode("ascii", errors="replace")
        virtual_size, virtual_address, raw_size, raw_offset = struct.unpack_from("<IIII", data, off + 8)
        sections.append(
            Section(
                name,
                image_base + virtual_address,
                raw_offset,
                max(virtual_size, raw_size),
                raw_size,
            )
        )

    return BinaryImage(path, "PE", 32, image_base + entry_rva, image_base, data, sections)


def load_image(path: Path) -> BinaryImage:
    data = path.read_bytes()
    if data[:4] == b"\x7fELF":
        return parse_elf32(path, data)
    if data[:2] == b"MZ":
        return parse_pe32(path, data)
    raise ValueError(f"{path} is not an ELF or PE image")


def nearest_prologue(image: BinaryImage, va: int, max_back: int = 0x3000) -> Optional[int]:
    text = image.section(".text")
    if text is None:
        text = image.section("CODE")
    if text is None:
        return None
    offset = image.va_to_offset(va)
    if offset is None:
        return None
    start = max(text.offset, offset - max_back)
    blob = image.data[start:offset]
    hit = blob.rfind(b"\x55\x89\xE5")
    if hit < 0:
        return None
    return image.offset_to_va(start + hit)


def find_c_string(image: BinaryImage, text: str) -> Optional[int]:
    encoded = text.encode("ascii")
    for suffix in (b"\0", b"\n\0", b"\r\n\0"):
        offsets = image.find_bytes(encoded + suffix)
        if offsets:
            return image.offset_to_va(offsets[0])
    return None


def xrefs_to(image: BinaryImage, va: int, section_names: Iterable[str] = (".text",)) -> list[int]:
    refs = []
    for offset in image.find_bytes(u32(va), section_names):
        ref_va = image.offset_to_va(offset)
        if ref_va is not None:
            refs.append(ref_va)
    return refs


def relative_call_xrefs_to(image: BinaryImage, va: int, section_names: Iterable[str] = (".text",)) -> list[int]:
    names = set(section_names)
    refs: list[int] = []
    for section in image.sections:
        if section.name not in names or section.raw_size <= 5:
            continue
        blob = image.data[section.offset : section.offset + section.raw_size]
        for index in range(0, len(blob) - 4):
            if blob[index] != 0xE8:
                continue
            disp = struct.unpack_from("<i", blob, index + 1)[0]
            ref_va = section.va + index
            if ref_va + 5 + disp == va:
                refs.append(ref_va)
    return refs


def find_function_by_pattern(image: BinaryImage, pattern: bytes) -> tuple[Optional[int], Optional[int]]:
    hits = image.find_bytes(pattern, (".text",))
    if not hits:
        return None, None
    hit_va = image.offset_to_va(hits[0])
    if hit_va is None:
        return None, None
    return nearest_prologue(image, hit_va) or hit_va, hit_va


@dataclass
class TargetReport:
    name: str
    status: str
    linux_va: Optional[int]
    windows_analog: str
    evidence: list[str]

    def as_json(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "linux_va": hex32(self.linux_va),
            "windows_analog": self.windows_analog,
            "evidence": self.evidence,
        }


def status_from(required: list[bool], optional: Optional[list[bool]] = None) -> str:
    optional = optional or []
    if all(required) and all(optional):
        return "confirmed"
    if all(required):
        return "candidate"
    return "missing"


def has_bytes(image: BinaryImage, va: int, size: int, needle: bytes) -> bool:
    return needle in image.read_va(va, size)


def first_or_none(values: list[int]) -> Optional[int]:
    return values[0] if values else None


def analyze_linux(image: BinaryImage) -> dict[str, object]:
    string_names = {
        "quickbar_panel": "14CPanelQuickBar",
        "quickbar_button": "15CGuiQuickButton",
        "chat_window": "20CGuiInGameChatWindow",
        "chat_dialog": "20CGuiInGameChatDialog",
        "gui_walkto": "gui_walkto",
        "gui_nowalk": "gui_nowalk",
        "walk_to_waypoint_log": "Client calls walktowaypoint %d",
        "chat_console": "**Console**: ",
        "chat_tellplayer": "tellplayer",
        "chat_window_log": "[CHAT WINDOW TEXT] [%s] %s",
        "server_app_type": "13CServerExoApp",
        "quickbar_object_type": "QBObjectType",
        "attack_mode": "AttackMode",
    }
    strings = {}
    for key, text in string_names.items():
        va = find_c_string(image, text)
        strings[key] = {
            "text": text,
            "va": hex32(va),
            "xrefs": [hex32(xref) for xref in xrefs_to(image, va)] if va is not None else [],
        }

    targets: list[TargetReport] = []

    vtable_writes = image.find_bytes(b"\xC7\x40\x20" + u32(0x0862F900), (".text",))
    ctor_hit = image.offset_to_va(vtable_writes[0]) if vtable_writes else None
    ctor = nearest_prologue(image, ctor_hit) if ctor_hit is not None else None
    ctor_has_stride = ctor is not None and any(
        has_bytes(image, ctor, 0x80, pattern)
        for pattern in (
            b"\x81\xC6\x84\x01\x00\x00",
            b"\x81\xC7\x84\x01\x00\x00",
            b"\x81\xC5\x84\x01\x00\x00",
        )
    )
    ctor_required = [
        ctor is not None,
        ctor_hit is not None,
        ctor is not None and has_bytes(image, ctor, 0x80, b"\x83\xC3\x74"),
        ctor_has_stride,
    ]
    targets.append(
        TargetReport(
            "quickbar.constructor",
            status_from(ctor_required),
            ctor,
            "Windows CPanelQuickBar layout anchor near kExpectedQuickbarVtable=0x008AB6D0",
            [
                f"vtable write at {hex32(ctor_hit)} stores 0x0862F900 to panel+0x20",
                "slot array anchor +0x74",
                "slot stride anchor +0x184",
            ],
        )
    )

    exec_pattern = (
        b"\x0F\xB6\x55\x0C"
        b"\x8D\x04\x52"
        b"\x8B\x4D\x08"
        b"\xC1\xE0\x05"
        b"\x01\xD0"
        b"\x8B\x91\x04\x37\x00\x00"
        b"\x8D\x04\x82"
        b"\x89\x45\x08"
        b"\xC9"
        b"\xE9"
    )
    quickbar_exec, quickbar_exec_hit = find_function_by_pattern(image, exec_pattern)
    targets.append(
        TargetReport(
            "quickbar.exec",
            status_from([quickbar_exec is not None]),
            quickbar_exec,
            "kExpectedQuickbarExec=0x0051FAA0",
            [
                f"slot-index math pattern at {hex32(quickbar_exec_hit)} computes slot * 0x184 + panel.currentPage",
                "tail-jumps into quickbar.slot_dispatch without touching the slot-reset helper",
            ],
        )
    )

    page_select_pattern = (
        b"\x8A\x45\x0C"
        b"\x3C\x02"
        b"\x88\x85\xE7\xFE\xFF\xFF"
        b"\x0F\x87\xBB\x00\x00\x00"
        b"\x0F\xB6\xC0"
        b"\x8D\x14\xC0"
        b"\x8D\x14\xD0"
        b"\xC1\xE2\x02"
        b"\x29\xC2"
        b"\xC1\xE2\x04"
    )
    quickbar_page_select, page_select_hit = find_function_by_pattern(image, page_select_pattern)
    page_select_required = [
        quickbar_page_select is not None,
        quickbar_page_select is not None and has_bytes(image, quickbar_page_select, 0xA0, b"\x8B\x91\x04\x37\x00\x00"),
        quickbar_page_select is not None and has_bytes(image, quickbar_page_select, 0xA0, b"\x89\x81\x04\x37\x00\x00"),
    ]
    targets.append(
        TargetReport(
            "quickbar.page_select",
            status_from(page_select_required),
            quickbar_page_select,
            "kExpectedQuickbarPageSelect=0x0051FD10",
            [
                f"page-select pattern at {hex32(page_select_hit)} accepts pages 0..2",
                "current page base is stored at panel+0x3704",
                "page stride is 0x1230",
            ],
        )
    )

    dispatch_pattern = (
        b"\x8B\x55\x08"
        b"\x8A\x42\x04"
        b"\x83\xF0\x01"
        b"\x83\xE0\x01"
        b"\x0F\x84"
    )
    quickbar_dispatch, dispatch_hit = find_function_by_pattern(image, dispatch_pattern)
    dispatch_required = [
        quickbar_dispatch is not None,
        quickbar_dispatch is not None and has_bytes(image, quickbar_dispatch, 0x80, b"\x0F\xB6\x82\xA0\x00\x00\x00"),
        quickbar_dispatch is not None and has_bytes(image, quickbar_dispatch, 0x80, b"\xFF\x24\x85\x90\x8D\x5F\x08"),
    ]
    targets.append(
        TargetReport(
            "quickbar.slot_dispatch",
            status_from(dispatch_required),
            quickbar_dispatch,
            "kExpectedQuickbarSlotDispatch=0x005164A0",
            [
                f"entry pattern at {hex32(dispatch_hit)} checks the quickbutton enabled flag",
                "slot type is read from slot+0xA0",
                "switch table anchor 0x085F8D90",
            ],
        )
    )

    chat_console_va = find_c_string(image, "**Console**: ")
    chat_console_xref = first_or_none(xrefs_to(image, chat_console_va)) if chat_console_va is not None else None
    chat_send = nearest_prologue(image, chat_console_xref) if chat_console_xref is not None else None
    tellplayer_va = find_c_string(image, "tellplayer")
    tellplayer_xrefs = xrefs_to(image, tellplayer_va) if tellplayer_va is not None else []
    chat_send_optional = [
        any(chat_send is not None and chat_send <= xref < chat_send + 0x1800 for xref in tellplayer_xrefs)
    ]
    targets.append(
        TargetReport(
            "chat.send",
            status_from([chat_send is not None], chat_send_optional),
            chat_send,
            "kExpectedChatSend=0x0057C9F0",
            [
                f"'**Console**: ' xref at {hex32(chat_console_xref)}",
                "'tellplayer' slash-command path is in the same large parser" if chat_send_optional[0] else "'tellplayer' path not confirmed in parser window",
            ],
        )
    )

    chat_log_va = find_c_string(image, "[CHAT WINDOW TEXT] [%s] %s")
    chat_log_xref = first_or_none(xrefs_to(image, chat_log_va)) if chat_log_va is not None else None
    chat_log = nearest_prologue(image, chat_log_xref) if chat_log_xref is not None else None
    targets.append(
        TargetReport(
            "chat.window_log",
            status_from([chat_log is not None]),
            chat_log,
            "kExpectedChatWindowLog=0x00493BD0",
            [f"'[CHAT WINDOW TEXT] [%s] %s' xref at {hex32(chat_log_xref)}"],
        )
    )

    gui_walkto_va = find_c_string(image, "gui_walkto")
    gui_nowalk_va = find_c_string(image, "gui_nowalk")
    walk_log_va = find_c_string(image, "Client calls walktowaypoint %d")
    gui_walkto_refs = xrefs_to(image, gui_walkto_va) if gui_walkto_va is not None else []
    gui_nowalk_refs = xrefs_to(image, gui_nowalk_va) if gui_nowalk_va is not None else []
    walk_log_refs = xrefs_to(image, walk_log_va) if walk_log_va is not None else []
    walk_function = nearest_prologue(image, first_or_none(gui_nowalk_refs)) if gui_nowalk_refs else None
    walk_required = walk_function is not None and bool(gui_walkto_refs) and bool(gui_nowalk_refs)
    targets.append(
        TargetReport(
            "movement.walk_to_waypoint",
            "candidate" if walk_required else "missing",
            walk_function,
            "kExpectedWalkToWaypoint=0x00407D70 plus kExpectedWalkNoWalkBlock=0x0042A7AB",
            [
                f"'gui_walkto' refs: {', '.join(hex32(x) for x in gui_walkto_refs) or 'none'}",
                f"'gui_nowalk' refs: {', '.join(hex32(x) for x in gui_nowalk_refs) or 'none'}",
                f"'Client calls walktowaypoint %d' refs: {', '.join(hex32(x) for x in walk_log_refs) or 'none'}",
                "candidate no-walk block starts at 0x0807E84A; candidate bypass target is 0x0807E878",
            ],
        )
    )

    app_global_xrefs = xrefs_to(image, 0x0862C354)
    targets.append(
        TargetReport(
            "app.global_slot",
            status_from([bool(app_global_xrefs)]),
            0x0862C354,
            "kAppGlobalSlotAddress=0x0092DC50",
            [f"absolute references in .text: {len(app_global_xrefs)}"],
        )
    )

    current_player = 0x08076A9C if has_bytes(
        image,
        0x08076A9C,
        0x20,
        b"\x8B\x45\x08\x8B\x40\x04\x89\x45\x08\xC9\xE9",
    ) else None
    current_object_id = 0x08076ACC if has_bytes(
        image,
        0x08076ACC,
        0x18,
        b"\x8B\x45\x08\x8B\x40\x04\x8B\x40\x24",
    ) else None
    targets.append(
        TargetReport(
            "identity.current_player",
            status_from([current_player is not None, current_object_id is not None]),
            current_player,
            "kExpectedCurrentPlayerResolver=0x00407850",
            [
                f"resolver wrapper at {hex32(current_player)}",
                f"active object-id helper at {hex32(current_object_id)} reads app object +0x24",
            ],
        )
    )

    player_name_pattern = (
        b"\x8B\x45\x0C"
        b"\x8B\x5D\x08"
        b"\xFF\xB0\xBC\x02\x00\x00"
        b"\x53"
        b"\xE8"
    )
    player_name_builder, player_name_hit = find_function_by_pattern(image, player_name_pattern)
    nwn_string_destroy = 0x085A61DC if has_bytes(
        image,
        0x085A61DC,
        0x30,
        b"\x8B\x5D\x08\x8B\x03\x85\xC0\x8B\x75\x0C",
    ) else None
    targets.append(
        TargetReport(
            "identity.player_name_builder",
            status_from([player_name_builder is not None, nwn_string_destroy is not None]),
            player_name_builder,
            "kExpectedPlayerNameBuilder=0x004CEF20 / kExpectedNwnStringDestroy=0x005BA420",
            [
                f"builder wrapper pattern at {hex32(player_name_hit)} reads player+0x2BC",
                f"NWN string destroy at {hex32(nwn_string_destroy)}",
            ],
        )
    )

    current_gui = 0x08077008 if has_bytes(
        image,
        0x08077008,
        0x18,
        b"\x8B\x45\x08\x8B\x40\x04\x8B\x40\x48",
    ) else None
    targets.append(
        TargetReport(
            "gui.current",
            status_from([current_gui is not None]),
            current_gui,
            "Linux helper used instead of a Windows exported analog",
            ["returns app object +0x48"],
        )
    )

    object_by_id = 0x08076B64 if has_bytes(
        image,
        0x08076B64,
        0x18,
        b"\x8B\x45\x08\x8B\x40\x04\x89\x45\x08\xC9\xE9",
    ) else None
    server_object_by_id = 0x082AA024 if has_bytes(
        image,
        0x082AA024,
        0x18,
        b"\x8B\x45\x08\x8B\x40\x04\x89\x45\x08\xC9\xE9",
    ) else None
    targets.append(
        TargetReport(
            "object.lookup",
            status_from([object_by_id is not None, server_object_by_id is not None]),
            object_by_id,
            "kExpectedObjectByIdResolver=0x004078C0 / kExpectedServerObjectByIdResolver=0x005FFAA0",
            [
                f"client object resolver wrapper at {hex32(object_by_id)}",
                f"server object resolver wrapper at {hex32(server_object_by_id)}",
            ],
        )
    )

    toggle_message = 0x081C4F44 if (
        has_bytes(image, 0x081C4F44, 0x20, b"\x55\x89\xE5\x56\x53\x83\xEC\x10") and
        has_bytes(image, 0x081C4F44, 0x90, b"\x80\xFB\x05\x75") and
        has_bytes(image, 0x081C4F44, 0x90, b"\x6A\x0A\x6A\x06")
    ) else None
    toggle_message_refs = relative_call_xrefs_to(image, toggle_message) if toggle_message is not None else []
    toggle_input = 0x081365CC if (
        toggle_message is not None and
        has_bytes(image, 0x081365CC, 0x20, b"\x55\x89\xE5\x57\x56\x53\x83\xEC\x1C") and
        has_bytes(image, 0x081365CC, 0x30, b"\x8B\x7D\x0C\x85\xFF") and
        0x08136673 in toggle_message_refs
    ) else None
    targets.append(
        TargetReport(
            "action_mode.toggle_input",
            status_from([toggle_input is not None]),
            toggle_input,
            "kExpectedToggleModeInput=0x004D00B0",
            [
                f"toggle-message writer at {hex32(toggle_message)} writes major=6 minor=10",
                f"relative call refs to writer: {', '.join(hex32(x) for x in toggle_message_refs) or 'none'}",
                "wrapper reads mode from stack arg +0x0C and calls the writer at 0x08136673",
            ],
        )
    )

    defensive_state_branch = 0x08157DD0 if (
        has_bytes(image, 0x08157DD0, 0x20, b"\xF7\x45\x10\x00\x00\x02\x00") and
        has_bytes(image, 0x08157DD0, 0x400, b"\xF7\xC7\x00\x04\x00\x00") and
        has_bytes(image, 0x08157DD0, 0x400, b"\x8B\xB0\x88\x01\x00\x00") and
        has_bytes(image, 0x08157DD0, 0x400, b"\xC7\x81\x88\x01\x00\x00\x01\x00\x00\x00") and
        has_bytes(image, 0x08157DD0, 0x400, b"\xC7\x81\x88\x01\x00\x00\x00\x00\x00\x00")
    ) else None
    targets.append(
        TargetReport(
            "action_mode.defensive_state",
            status_from([defensive_state_branch is not None]),
            defensive_state_branch,
            "Windows creature-update parser maps update mask 0x20000 bit 0x400 to client flag +0x184",
            [
                "Linux creature-update branch tests update mask 0x20000",
                "incoming activity bit 0x400 maps to client player +0x188",
                "branch writes DWORD 1/0 for Defensive Casting on/off feedback",
            ],
        )
    )

    section_summary = [
        {
            "name": section.name,
            "va": hex32(section.va),
            "offset": hex32(section.offset),
            "size": hex32(section.size),
        }
        for section in image.sections
        if section.name in {".text", ".rodata", ".data", ".bss"}
    ]

    return {
        "path": str(image.path),
        "kind": image.kind,
        "bits": image.bits,
        "entry": hex32(image.entry),
        "sections": section_summary,
        "strings": strings,
        "targets": [target.as_json() for target in targets],
    }


WINDOWS_PATTERNS: dict[str, tuple[int, bytes, str]] = {
    "quickbar.exec": (
        0x0051FAA0,
        bytes.fromhex("8b 44 24 04 8b 89 b8 2b 00 00 25 ff 00 00 00"),
        "kExpectedQuickbarExec=0x0051FAA0",
    ),
    "quickbar.slot_dispatch": (
        0x005164A0,
        bytes.fromhex("56 8b f1 8b 46 04 f7 d0 a8 01"),
        "kExpectedQuickbarSlotDispatch=0x005164A0",
    ),
    "chat.send": (
        0x0057C9F0,
        bytes.fromhex("6a ff 68 b8 76 88 00 64 a1"),
        "kExpectedChatSend=0x0057C9F0",
    ),
    "chat.window_log": (
        0x00493BD0,
        bytes.fromhex("6a ff 68 1e 2d 87 00 64 a1"),
        "kExpectedChatWindowLog=0x00493BD0",
    ),
    "movement.no_walk_block": (
        0x0042A7AB,
        bytes.fromhex("6a 00 83 ec 10 8b cc"),
        "kExpectedWalkNoWalkBlock=0x0042A7AB",
    ),
}


def analyze_diamond(image: BinaryImage) -> dict[str, object]:
    targets = []
    for name, (va, pattern, analog) in WINDOWS_PATTERNS.items():
        actual = image.read_va(va, len(pattern))
        targets.append(
            {
                "name": name,
                "status": "confirmed" if actual == pattern else "missing",
                "windows_va": hex32(va),
                "analog": analog,
            }
        )
    return {
        "path": str(image.path),
        "kind": image.kind,
        "bits": image.bits,
        "entry": hex32(image.entry),
        "image_base": hex32(image.image_base),
        "targets": targets,
    }


def print_report(report: dict[str, object], diamond_report: Optional[dict[str, object]] = None) -> None:
    print(f"Linux client: {report['path']}")
    print(f"  format: {report['kind']}{report['bits']} entry={report['entry']}")
    print("  sections:")
    for section in report["sections"]:  # type: ignore[index]
        print(f"    {section['name']:8} va={section['va']} off={section['offset']} size={section['size']}")

    print("\nLinux hook targets:")
    for target in report["targets"]:  # type: ignore[index]
        print(f"  [{target['status']}] {target['name']:26} {target['linux_va'] or 'n/a'}")
        print(f"      analog: {target['windows_analog']}")
        for item in target["evidence"]:
            print(f"      - {item}")

    print("\nString anchors:")
    for key, item in report["strings"].items():  # type: ignore[index]
        xrefs = ", ".join(item["xrefs"][:4])
        if len(item["xrefs"]) > 4:
            xrefs += f", ... ({len(item['xrefs'])} total)"
        print(f"  {key:22} {item['va'] or 'n/a'} refs={xrefs or 'none'}")

    if diamond_report is not None:
        print(f"\nDiamond reference: {diamond_report['path']}")
        print(
            f"  format: {diamond_report['kind']}{diamond_report['bits']} "
            f"base={diamond_report['image_base']} entry={diamond_report['entry']}"
        )
        for target in diamond_report["targets"]:  # type: ignore[index]
            print(f"  [{target['status']}] {target['name']:26} {target['windows_va']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--linux-client",
        type=Path,
        default=DEFAULT_LINUX_CLIENT,
        help="Path to the Linux nwmain ELF client.",
    )
    parser.add_argument(
        "--diamond-exe",
        type=Path,
        default=DEFAULT_DIAMOND_EXE if DEFAULT_DIAMOND_EXE.exists() else None,
        help="Optional path to the Windows Diamond nwmain.exe for reference validation.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    linux_image = load_image(args.linux_client)
    linux_report = analyze_linux(linux_image)

    diamond_report = None
    if args.diamond_exe is not None:
        diamond_image = load_image(args.diamond_exe)
        diamond_report = analyze_diamond(diamond_image)

    if args.json:
        print(json.dumps({"linux": linux_report, "diamond": diamond_report}, indent=2))
    else:
        print_report(linux_report, diamond_report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
