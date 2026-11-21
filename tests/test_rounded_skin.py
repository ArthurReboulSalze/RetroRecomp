"""The rounded skin (retrorecomp/rounded_skin.py): every ttk style the converter uses is skinned at 8 px, in a withdrawn Tk window.

It guards what made the first prototype 5x to 40x slower (a narrow 9-slice middle, which Tk tiles, and one state entry per state
combination, which Tk instantiates per widget), the focus ring that replaces the dotted line, the colour of the corners, the layout
that must not move, and the picture sizes at Tk scaling 1.0, 1.5 and 2.0."""
import os
import tkinter as tk
import unittest
from tests.tk_cleanup import release_tk
from tkinter import ttk
from unittest.mock import patch

from retrorecomp import rounded_skin
from retrorecomp.branding import COLORS, apply_theme
from retrorecomp.rounded_skin import apply_rounded_theme
from retrorecomp.rounded_ui import Look
from retrorecomp.rounded_skin import CENTER, RADIUS, Skin, skin_of
from retrorecomp.ui_fonts import ui_scale
from tests.test_window_scale import tk_rounding

WIDGETS = (('TButton', ttk.Button), ('Primary.TButton', ttk.Button), ('TEntry', ttk.Entry), ('TCombobox', ttk.Combobox),
           ('TSpinbox', ttk.Spinbox), ('TCheckbutton', ttk.Checkbutton), ('TLabelframe', ttk.LabelFrame),
           ('Vertical.TScrollbar', ttk.Scrollbar))


def tk_root(test):
    """A withdrawn root, or the test skipped where there is no display (a Linux runner without $DISPLAY)."""
    try:
        root = tk.Tk()
    except tk.TclError:
        test.skipTest('no display')
    root.withdraw()
    return root


def applied_factor(root):
    """The scale Tk applied (`tk scaling` read back over 96 dpi), not the one a test asked for: see tk_rounding."""
    return float(root.tk.call('tk', 'scaling')) * 72 / 96


def restore_scaling(test, root):
    """`tk scaling` belongs to the display, not to the interpreter: a test that changes it must put it back for the next one."""
    original = float(root.tk.call('tk', 'scaling'))
    test.addCleanup(lambda: root.tk.call('tk', 'scaling', original))


def requested(root):
    """(style, width, height) of one widget of each style, as the layout asks for them."""
    out = {}
    for name, widget_class in WIDGETS:
        kw = {'orient': 'vertical'} if widget_class is ttk.Scrollbar else {'text': 'Abc'} if widget_class in (
            ttk.Button, ttk.Checkbutton, ttk.LabelFrame) else {}
        widget = widget_class(root, style=name, **kw)
        widget.pack()
        root.update_idletasks()
        out[name] = (widget.winfo_reqwidth(), widget.winfo_reqheight())
        widget.destroy()
    return out


class SkinCase(unittest.TestCase):
    def setUp(self):
        release_tk(self)                      # first: its cleanup runs after root.destroy (tests/tk_cleanup.py)
        self.root = tk_root(self)
        self.addCleanup(self.root.destroy)
        apply_rounded_theme(self.root, 'Segoe UI')
        self.style = ttk.Style(self.root)
        self.skin = skin_of(self.root)

    def layout(self, name):
        return str(self.style.layout(name))


class AppliedByTheTheme(SkinCase):
    def test_the_converter_theme_installs_the_skin_at_8_px(self):
        self.assertIsInstance(self.skin, Skin)
        self.assertEqual(RADIUS, 8)
        self.assertEqual(self.skin.radius, 8)

    def test_every_kind_of_widget_gets_a_rounded_layout_when_its_first_widget_is_built(self):
        for name, widget_class in WIDGETS:
            kw = {'orient': 'vertical'} if widget_class is ttk.Scrollbar else {}
            widget_class(self.root, style=name, **kw)
            self.assertIn(self.skin.tag + '.', self.layout(name), name)
        self.assertIn(f'{self.skin.tag}.btn.TButton', self.layout('TButton'))

    def test_a_style_a_window_configures_for_itself_is_skinned_too(self):
        self.style.configure('Zed.Toolbar.TButton', background='#123456', padding=(3, 3))
        ttk.Button(self.root, style='Zed.Toolbar.TButton', text='x')
        self.assertIn(f'{self.skin.tag}.btn.Zed.Toolbar.TButton', self.layout('Zed.Toolbar.TButton'))
        self.assertEqual(self.skin.looks['Zed.Toolbar.TButton']([])[0], '#123456')      # its colour is read, not copied

    def test_the_focus_ring_is_in_the_picture_not_the_dotted_line(self):
        for name in ('TButton', 'Primary.TButton'):
            ttk.Button(self.root, style=name)
            self.assertNotIn('Button.focus', self.layout(name))
            self.assertIn('Button.label', self.layout(name))
        gold = self.skin.looks['Primary.TButton']
        dark = self.skin.looks['TButton']
        self.assertEqual(dark(['focus'])[2], COLORS['gold'])               # gold ring on a dark button
        self.assertEqual(gold(['focus'])[2], '#f5f5f4')                     # light ring on the gold one, which was invisible
        self.assertIsNone(dark([])[2])
        self.assertIsNone(dark(['disabled'])[2])

    def test_every_state_of_a_button_exists(self):
        ttk.Button(self.root, style='Primary.TButton')
        ttk.Button(self.root, style='TButton')
        normal, hover, pressed, disabled = (self.skin.looks['TButton'](states) for states in ([], ['active'], ['pressed'], ['disabled']))
        self.assertEqual(normal[0], COLORS['button'])
        self.assertEqual(hover[0], COLORS['hover'])
        self.assertEqual(pressed[0], COLORS['selected'])
        self.assertEqual(disabled[0], COLORS['panel'])
        self.assertEqual(len({normal, hover, pressed, disabled}), 4)
        gold = self.skin.looks['Primary.TButton']
        self.assertEqual((gold([])[0], gold(['active'])[0]), (COLORS['gold'], COLORS['gold_hover']))
        self.assertEqual(gold(['disabled'])[0], COLORS['panel'])
        self.assertNotEqual(gold(['focus', 'active']), gold(['active']))     # the ring shows while hovered too

    def test_fields_have_disabled_readonly_and_focus_pictures(self):
        for name, widget_class in (('TEntry', ttk.Entry), ('TCombobox', ttk.Combobox), ('TSpinbox', ttk.Spinbox)):
            widget_class(self.root, style=name)
            self.assertTrue(self.layout(name).count(self.skin.tag + '.'), name)
        self.assertIn('Combobox.textarea', self.layout('TCombobox'))
        self.assertNotIn('Combobox.downarrow', self.layout('TCombobox'))     # one rounded field, the chevron inside it
        entry = next(e for e in self.skin.entries if e.endswith('field.entry.TEntry'))
        self.assertGreaterEqual(self.skin.entries[entry], 3)                 # normal, focus, disabled


def element_names(layout):
    """Every element name of a ttk layout, children included."""
    names = []
    for name, options in layout:
        names.append(name)
        names.extend(element_names(options.get('children', [])))
    return names


class ElementsTkFindsByName(SkinCase):
    """Tk finds some elements by the END of their name (Arthur, 20 Nov 2026: every scrollbar was one long bar with no thumb to drag):
    the scrollbar sizes and drags the element matching `*thumb` (its C code, and `switch -glob ... *thumb` in scrollbar.tcl), the
    spinbox steps on `*uparrow` / `*downarrow` (spinbox.tcl). A withdrawn window answers no identify(), so the names are checked
    with Tcl's own `string match`; tools/gui_smoke.py and the hidden-desktop captures show the thumb sized and dragged."""

    def matches(self, pattern, layout):
        return [name for name in element_names(layout) if self.root.tk.call('string', 'match', pattern, name)]

    def test_every_skinned_scrollbar_keeps_one_thumb(self):
        for name in ('Vertical.TScrollbar', 'Slim.Vertical.TScrollbar', 'Horizontal.TScrollbar'):
            orient = 'horizontal' if name.startswith('Horizontal') else 'vertical'
            bar = ttk.Scrollbar(self.root, orient=orient, style=name)
            layout = self.style.layout(str(bar.cget('style')) or name)
            thumbs = self.matches('*thumb', layout)
            self.assertEqual(len(thumbs), 1, (name, element_names(layout)))
            self.assertTrue(thumbs[0].startswith(self.skin.tag + '.'), thumbs)      # the rounded picture, not clam's
            self.assertEqual(self.matches('*trough', layout), [f'{orient.title()}.Scrollbar.trough'])

    def test_the_spinbox_arrows_keep_their_names(self):
        spin = ttk.Spinbox(self.root, from_=1, to=9)
        layout = self.style.layout(str(spin.cget('style')) or 'TSpinbox')
        for pattern in ('*uparrow', '*downarrow', '*textarea'):
            self.assertEqual(len(self.matches(pattern, layout)), 1, (pattern, element_names(layout)))
        self.assertTrue(self.matches('*uparrow', layout)[0].startswith(self.skin.tag + '.'))

    def test_a_dragged_thumb_shows_it(self):
        bar = ttk.Scrollbar(self.root, orient='vertical')
        name = str(bar.cget('style')) or 'Vertical.TScrollbar'
        thumb = next(e for e in self.skin.entries if e.endswith(name + '.thumb'))
        self.assertEqual(self.skin.entries[thumb], 3)       # normal, hover, pressed: three different pictures


class TheCostsStayDown(SkinCase):
    """The two fixes that kept 60 buttons near 160-240 ms (the prototype took over a second)."""

    def build_all(self):
        for name, widget_class in WIDGETS:
            kw = {'orient': 'vertical'} if widget_class is ttk.Scrollbar else {}
            widget_class(self.root, style=name, **kw)
        ttk.Button(self.root, style='Toolbar.Primary.TButton')
        ttk.Button(self.root, style='Toolbar.TButton')

    def test_the_stretched_middle_is_one_wide_slice_and_the_minimum_size_is_the_corners(self):
        self.build_all()
        self.assertEqual(CENTER, 24)
        self.assertTrue(self.skin.sizes)
        for element, (side, minimum) in self.skin.sizes.items():
            self.assertEqual(side - minimum, CENTER, element)      # corners + 24 px middle: Tk tiles it, few draws
            self.assertLess(minimum, side, element)
            self.assertLessEqual(side, 2 * 14 + 2 + CENTER + 2, element)        # radius 8, never over 14 at 100 %

    def test_state_entries_are_pruned(self):
        self.build_all()
        counts = {element: count for element, count in self.skin.entries.items()}
        self.assertTrue(counts)
        self.assertLessEqual(counts[f'{self.skin.tag}.btn.TButton'], 10)           # 16 combinations of state were 16 entries
        self.assertLessEqual(counts[f'{self.skin.tag}.btn.Primary.TButton'], 6)
        for element, count in counts.items():
            self.assertLessEqual(count, 10, element)
            self.assertGreaterEqual(count, 1, element)
        for element in counts:
            if '.field.' in element:
                self.assertLessEqual(counts[element], 5, element)

    def test_prune_drops_only_what_changes_nothing(self):
        a, b, c = object(), object(), object()
        specs = [('pressed', 'active', c), ('pressed', c), ('active', b), ('focus', a), ('selected', a)]
        kept = Skin.prune(a, specs)
        self.assertEqual([spec[:-1] for spec in kept], [('pressed',), ('active',)])

    def test_the_window_cards_and_segments_have_a_wide_middle_too(self):
        # rounded_ui's cards had a 2 px middle: ttk tiled it ~100,000 times per redraw of an 800 x 500 card, so the Multiplayer
        # window took 2 to 4 s per redraw and froze at every activation change (opening its game list; Arthur, 19 Nov 2026)
        from retrorecomp.rounded_ui import CARD_CENTER
        look = Look(self.root, COLORS, 'Segoe UI')
        for make, radius, middle in ((lambda: look.card('WideT1', '#222222', '#111111', 16), 16, CARD_CENTER),
                                     (lambda: look.segment('WideT2', '#111111', '#d4a737', '#333333'), 13, CENTER)):
            before = len(look.images)
            make()
            self.assertGreater(len(look.images), before)
            for picture in look.images[before:]:
                self.assertEqual(picture.width() - 2 * (radius + 1), middle)
        self.assertGreaterEqual(CARD_CENTER, 64)

    def test_one_picture_serves_every_style_that_looks_the_same(self):
        self.build_all()
        before = self.skin.pictures
        ttk.Button(self.root, style='TButton')
        ttk.Button(self.root, style='Primary.TButton')
        self.assertEqual(self.skin.pictures, before)                 # nothing new: the pictures are shared, not made per button


class CornersAndSurfaces(SkinCase):
    def test_a_style_on_another_surface_gets_a_derived_name(self):
        ttk.Button(self.root, text='on the window')
        panel = tk.Frame(self.root, bg='#2b2b2b')
        on_panel = ttk.Button(panel, text='on a panel')
        self.assertEqual(str(on_panel.cget('style')), 'Rs2b2b2b.TButton')
        self.assertEqual(self.skin.derived_from['Rs2b2b2b.TButton'], 'TButton')
        self.assertEqual(self.skin.surfaces['Rs2b2b2b.TButton'], '#2b2b2b')
        self.assertEqual(self.skin.surfaces['TButton'], self.skin.lookup('.', 'background'))
        self.assertEqual(self.skin.looks['Rs2b2b2b.TButton']([])[0], COLORS['button'])        # everything else is inherited
        self.assertNotEqual(self.layout('Rs2b2b2b.TButton'), self.layout('TButton'))
        again = ttk.Button(panel, text='again')
        self.assertEqual(str(again.cget('style')), 'Rs2b2b2b.TButton')                       # made once

    def test_a_check_box_or_radio_button_on_a_panel_draws_the_panel_behind_its_label(self):
        panel = tk.Frame(self.root, bg='#292929')
        box = ttk.Checkbutton(panel, text='Tick')
        radio = ttk.Radiobutton(panel, text='Choose', value='a')
        self.assertEqual(str(box.cget('style')), 'Rs292929.TCheckbutton')
        self.assertEqual(str(radio.cget('style')), 'Rs292929.TRadiobutton')
        for name in ('Rs292929.TCheckbutton', 'Rs292929.TRadiobutton'):
            self.assertEqual(self.style.lookup(name, 'background'), '#292929')
            self.assertEqual(self.style.lookup(name, 'background', ['active']), '#292929')
        self.assertEqual(self.style.lookup('Rs292929.TCheckbutton', 'foreground'), COLORS['text'])     # the rest is inherited
        self.assertNotEqual(self.layout('Rs292929.TCheckbutton'), self.layout('TCheckbutton'))          # its tick is skinned too
        tag = 'rs%d.check.' % self.skin.generation
        self.assertEqual(self.skin.entries[tag + 'Rs292929.TCheckbutton'], self.skin.entries[tag + 'TCheckbutton'])   # as pruned as the plain one
        # The window's own surface, a style with a background of its own and a custom radio style are left alone.
        self.assertEqual(str(ttk.Checkbutton(self.root).cget('style')), 'TCheckbutton')
        self.assertEqual(str(ttk.Radiobutton(self.root).cget('style')), 'TRadiobutton')
        self.style.configure('Own.TCheckbutton', background='#101010')
        self.assertEqual(str(ttk.Checkbutton(panel, style='Own.TCheckbutton').cget('style')), 'Own.TCheckbutton')
        self.assertEqual(str(ttk.Radiobutton(panel, style='MpSeg.TRadiobutton').cget('style')), 'MpSeg.TRadiobutton')

    def test_the_window_background_keeps_the_plain_names(self):
        button = ttk.Button(self.root, style='Primary.TButton')
        self.assertEqual(str(button.cget('style')), 'Primary.TButton')
        entry = ttk.Entry(self.root)
        self.assertEqual(str(entry.cget('style')) or 'TEntry', 'TEntry')

    def test_a_card_gives_its_colour_to_what_stands_on_it(self):
        look = Look(self.root, COLORS, 'Segoe UI')
        look.card('TestCard', '#303030', '#232323', 14)
        card = ttk.Frame(self.root, style='TestCard.TFrame')
        entry = ttk.Entry(card)
        self.assertEqual(self.skin.surfaces[str(entry.cget('style'))], '#303030')

    def test_a_style_set_after_its_widget_was_built_is_skinned_by_restyle(self):
        bar = ttk.Scrollbar(self.root, orient='vertical')
        self.style.configure('Late.Vertical.TScrollbar', background='#2b2b2b', troughcolor='#232323')
        bar.configure(style='Late.Vertical.TScrollbar')
        self.skin.restyle(bar)
        self.assertIn(f'{self.skin.tag}.Late.Vertical.TScrollbar.thumb', self.layout('Late.Vertical.TScrollbar'))

    def test_scan_skins_widgets_built_before_the_skin(self):
        root = tk_root(self)
        self.addCleanup(root.destroy)
        with patch('retrorecomp.rounded_skin.install'):
            apply_rounded_theme(root, 'Segoe UI')
        self.assertIsNone(skin_of(root))
        button = ttk.Button(root, style='Primary.TButton')
        skin = rounded_skin.install(root)
        skin.scan()
        self.assertIn('btn.Primary.TButton', str(ttk.Style(root).layout('Primary.TButton')))
        self.assertEqual(str(button.cget('style')), 'Primary.TButton')


class OneMechanismForPills(SkinCase):
    """The Multiplayer window and the closing card ask the global skin for their buttons (rounded_ui.Look.pill_button)."""

    def test_a_pill_button_is_a_skinned_style_with_its_own_corners_and_radius(self):
        look = Look(self.root, COLORS, 'Segoe UI')
        name = look.pill_button('TestPill', '#d4a737', '#efc64f', '#191919', '#303030', 12, bold=True)
        self.assertEqual(name, 'TestPill.TButton')
        self.assertIs(look.skin, self.skin)
        self.assertIn(f'{self.skin.tag}.btn.TestPill.TButton', self.layout(name))
        self.assertEqual(self.skin.surfaces[name], '#303030')
        self.assertEqual(self.skin.records[(name, 'button')][:2], ('#303030', 12))
        self.assertEqual(self.skin.looks[name]([])[0], '#d4a737')
        self.assertEqual(self.skin.looks[name](['active'])[0], '#efc64f')
        self.assertEqual(self.skin.looks[name](['disabled'])[0], COLORS['panel'])
        self.assertFalse(hasattr(look, 'pill_images'))
        # on another surface it stays what its maker said
        other = tk.Frame(self.root, bg='#444444')
        self.assertEqual(str(ttk.Button(other, style=name).cget('style')), name)

    def test_the_outline_stays_in_every_state_but_disabled(self):
        look = Look(self.root, COLORS, 'Segoe UI')
        name = look.pill_button('TestGhost', '#232323', '#444444', '#b7b7b7', '#232323', 12, outline='#626262')
        for states in ([], ['active'], ['pressed']):
            self.assertEqual(self.skin.looks[name](states)[1], '#626262')
        self.assertNotEqual(self.skin.looks[name](['disabled'])[1], '#626262')

    def test_a_look_has_no_button_pictures_of_its_own(self):
        look = Look(self.root, COLORS, 'Segoe UI')
        before = len(look.images)
        look.pill_button('TestSolo', '#343434', '#444444', '#f5f5f4', '#232323', 12)
        self.assertEqual(len(look.images), before)


class DashedToggle(SkinCase):
    """The converter's view switch is a toggle: its border is dashed (Arthur, 19 Nov 2026), drawn in the skin's picture."""

    def test_the_dashes_cut_the_straight_middles_only_and_tile_without_a_seam(self):
        from retrorecomp.rounded_skin import box_image, dashed_box, rgb
        r, side = 8, 2 * 8 + 2 + CENTER
        picture = dashed_box(side, r, 2, '#d4a737', '#343434', '#232323')
        top = [picture.getpixel((x, 0)) for x in range(r + 1, r + 1 + CENTER)]
        gold, fill = rgb('#d4a737'), rgb('#343434')
        self.assertIn(gold, top)
        self.assertIn(fill, top)                                    # gaps show the button, not a hole
        self.assertEqual(top[:8], top[8:16])                        # the period divides the tiled middle
        left = [picture.getpixel((0, y)) for y in range(r + 1, r + 1 + CENTER)]
        self.assertEqual(left, top)
        solid = box_image(side, side, [(0, r, '#d4a737'), (2, r - 2, '#343434')], '#232323')
        for x in range(r + 1):                                      # the corners are whole
            self.assertEqual(picture.getpixel((x, 1)), solid.getpixel((x, 1)))

    def test_a_style_asking_for_dashes_gets_them(self):
        self.style.configure('Dash.TButton', background='#343434', bordercolor='#d4a737', rrdash=1)
        ttk.Button(self.root, text='x', style='Dash.TButton').pack()
        ttk.Button(self.root, text='x').pack()
        self.assertIn(('Dash.TButton', 'button'), self.skin.done)
        dashes = {key[7] for key in self.skin.cache if key[0] == 'btn'}
        self.assertEqual(dashes, {True, False})


class ThickBorder(SkinCase):
    """Convert's gold border two pixels thick (Arthur's mock-up, 20 Nov 2026): `rrline` sets the border's width."""

    def test_a_style_asking_for_a_thick_border_gets_it(self):
        self.style.configure('Thick.TButton', background='#181818', bordercolor='#d4a737', rrline=2)
        ttk.Button(self.root, text='x', style='Thick.TButton').pack()
        ttk.Button(self.root, text='x').pack()
        self.assertIn(('Thick.TButton', 'button'), self.skin.done)
        widths = {key[8] for key in self.skin.cache if key[0] == 'btn'}
        self.assertEqual(widths, {self.skin.px(1), self.skin.px(2)})


class LayoutDoesNotMove(unittest.TestCase):
    def test_no_widget_asks_for_another_size_than_before(self):
        # At 96 dpi (Windows always): a Linux display at about 100 dpi rounds the combobox chevron's 15 px up to 16.
        # The scaling is set BEFORE the two compared roots exist: a root sizes its own fonts at the display's scaling when
        # it is created, so on a screen that is not at 96 dpi (GitHub's Windows runner) a root made before the change
        # measured its text at the runner's dpi and the other at 96 (21 Nov 2026).
        display = tk_root(self)
        self.addCleanup(display.destroy)
        restore_scaling(self, display)
        display.tk.call('tk', 'scaling', 96 / 72)
        plain = tk_root(self)
        self.addCleanup(plain.destroy)
        apply_theme(plain, 'Segoe UI')                     # branding alone: square
        # The reference must itself be at 96 dpi. Tk's own clam elements (the check indicator, the spinbox arrows) can be
        # sized from the host's real dpi, not from `tk scaling`: on GitHub's Windows runner the square TCheckbutton was
        # 48 x 22 and TSpinbox 143 wide while the rounded ones measured exactly as on a 96 dpi PC (42 x 21, 141). A bare
        # check (no text) is 21 px wide at 96 dpi (Tk 8.6.15 on Windows, 8.6.16 on Linux); elsewhere there is no square
        # 96 dpi reference to compare with, and players never see the square theme.
        bare = ttk.Checkbutton(plain, text='')
        bare.pack()
        plain.update_idletasks()
        if bare.winfo_reqwidth() != 21:
            self.skipTest(f'the host draws Tk\'s own clam indicator at {bare.winfo_reqwidth()} px, not its 21 px at 96 dpi: '
                          'no square 96 dpi reference here')
        bare.destroy()
        square = requested(plain)
        rounded = tk_root(self)
        self.addCleanup(rounded.destroy)
        apply_rounded_theme(rounded, 'Segoe UI')
        self.assertEqual(requested(rounded), square)


class HiDpi(unittest.TestCase):
    """The pictures are pixel sizes: they follow `tk scaling` (1.0 is 96 dpi: 4/3 Tk scaling), built once at start."""

    def at(self, factor):
        root = tk_root(self)
        self.addCleanup(root.destroy)
        restore_scaling(self, root)
        root.tk.call('tk', 'scaling', factor * 96 / 72)
        apply_rounded_theme(root, 'Segoe UI')
        skin = skin_of(root)
        self.assert_follows(skin, root, factor)
        ttk.Button(root, style='TButton')
        ttk.Button(root, style='Primary.TButton')
        ttk.Entry(root)
        ttk.Checkbutton(root)
        return skin

    def assert_follows(self, skin, root, factor):
        """The skin is built at the scale Tk applied, exactly; that scale is the one asked for, within what Tk's whole
        millimetres keep of it (tests/test_window_scale.py tk_rounding: 2.0 reads 2.0069 on a 1024 px screen)."""
        self.assertAlmostEqual(skin.scale, ui_scale(root), places=9)
        self.assertAlmostEqual(applied_factor(root), factor, delta=factor * tk_rounding(root))

    def test_sizes_follow_the_scaling(self):
        sides = {}
        for factor in (1.0, 1.5, 2.0):
            skin = self.at(factor)
            button = f'{skin.tag}.btn.TButton'
            side, minimum = skin.sizes[button]
            radius = (minimum - 2) // 2
            self.assertEqual(side - minimum, CENTER)
            sides[factor] = (side, minimum)
        self.assertLess(sides[1.0][1], sides[1.5][1])
        self.assertLess(sides[1.5][1], sides[2.0][1])
        self.assertEqual(sides[1.0][1], 2 * (8 + 1))

    def test_the_ring_and_border_widths_scale(self):
        one, two = self.at(1.0), self.at(2.0)
        self.assertEqual((one.px(1), one.px(2), one.px(3)), (1, 2, 3))
        self.assertEqual((two.px(1), two.px(2), two.px(3)), (2, 4, 6))

    def test_the_scale_is_one_shared_helper_clamped_to_1_to_3(self):
        root = tk_root(self)
        self.addCleanup(root.destroy)
        restore_scaling(self, root)
        for scaling, expected in ((96 / 72, 1.0), (72 / 72, 1.0), (144 / 72, 1.5), (192 / 72, 2.0), (500 / 72, 3.0)):
            root.tk.call('tk', 'scaling', scaling)
            # The one definition, on what Tk applied: over 96 dpi, clamped to 1..3 ...
            self.assertAlmostEqual(ui_scale(root), min(3.0, max(1.0, applied_factor(root))), places=9)
            # ... which is the scale asked for, within Tk's whole millimetres (tk_rounding).
            self.assertAlmostEqual(ui_scale(root), expected, delta=expected * tk_rounding(root))
        self.assertEqual(ui_scale(object()), 1.0)

    def test_apply_theme_again_rebuilds_with_the_new_scaling_and_new_element_names(self):
        root = tk_root(self)
        self.addCleanup(root.destroy)
        restore_scaling(self, root)
        apply_rounded_theme(root, 'Segoe UI')
        skin = skin_of(root)
        ttk.Button(root, style='TButton')
        first = skin.tag
        root.tk.call('tk', 'scaling', 2.0 * 96 / 72)
        apply_rounded_theme(root, 'Segoe UI')
        self.assertIs(skin_of(root), skin)
        self.assertNotEqual(skin.tag, first)
        self.assert_follows(skin, root, 2.0)
        self.assertIn(f'{skin.tag}.btn.TButton', str(ttk.Style(root).layout('TButton')))


if __name__ == '__main__':
    unittest.main()


class FreedOnItsOwnThread(unittest.TestCase):
    def test_a_destroyed_root_is_freed_at_once_not_by_the_cycle_collector(self):
        # The skin and its root point at each other; left to the cycle collector, the interpreter could be freed from
        # another thread, which aborts the process (« Tcl_AsyncDelete: async handler deleted by the wrong thread »).
        import gc
        import weakref
        gc.collect()
        gc.disable()
        self.addCleanup(gc.enable)
        root = tk_root(self)
        apply_rounded_theme(root, 'Segoe UI')
        ttk.Button(root, text='x').pack()
        ttk.Entry(root).pack()
        root.update()
        gone = weakref.ref(root)
        root.destroy()
        del root
        self.assertIsNone(gone())


GC_IN_A_WORKER = r'''
import gc, sys, threading, tkinter as tk
from tkinter import ttk
sys.path.insert(0, sys.argv[1])
from retrorecomp.rounded_skin import apply_rounded_theme
gc.disable()
for _ in range(3):
    root = tk.Tk()
    root.withdraw()
    apply_rounded_theme(root, 'Segoe UI')
    for kind in (ttk.Button, ttk.Entry, ttk.Checkbutton, ttk.Combobox):
        kind(root).pack()
    root.update()
    root.destroy()
    del root
worker = threading.Thread(target=gc.collect)
worker.start()
worker.join()
print('alive')
'''


@unittest.skipUnless(os.environ.get('DISPLAY') or os.name == 'nt', 'needs a Tk display (kept hidden)')
class NoAbortWhenAWorkerCollects(unittest.TestCase):
    def test_a_destroyed_skinned_root_then_a_collection_in_a_worker_thread_does_not_abort(self):
        # A player's worker threads (the front-end's cover loader, the netplay workers) collect garbage while windows open
        # and close. A Tk interpreter freed from one of them aborts the process (« Tcl_AsyncDelete: async handler deleted by
        # the wrong thread »), so this runs in a child process: an abort there is a failed test, not a dead suite.
        import subprocess
        import sys
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, '-B', '-c', GC_IN_A_WORKER, str(root)], capture_output=True, text=True,
                                timeout=120, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.assertEqual((result.returncode, result.stdout.strip()), (0, 'alive'), result.stderr[-2000:])
