"""Gold/charcoal demoscene credits, rendered with bounded native Tk primitives.

No video, web view, frame-sized bitmap or image-generation dependency. Links
remain clickable; any wheel/key/scrollbar gesture hands scrolling to the user.
"""
from __future__ import annotations
import math
import random
import time
import tkinter as tk
from tkinter import ttk
import webbrowser

from . import __version__
from .branding import COLORS, wordmark_rectangles
from .credits_music import MusicSession
from .dialogs import center_dialog
from .paths import ASSETS, APP_NAME

BG = '#141414'
GOLD = COLORS['gold']
WHITE = COLORS['text']
MUTED = COLORS['muted']
BACKGROUND_SPEED = 4.0


class PercussionMotion:
    """Consume hit counters, never infer a hit from a sustained voice level."""
    def __init__(self):
        self.previous = (0, 0, 0)
        self.height = [0., 0.]
        self.velocity = [0., 0.]
        self.impact = [0., 0.]
        self.last_hit = [None, None]
        self.shimmer = 0.
        self.last_time = None

    def update(self, now, beats=(0,)*6, active=False):
        delta = min(.1, max(0., now-(self.last_time if self.last_time is not None else now)))
        self.last_time = now
        # Continue physics while muted, but consume counters so unmuting never
        # replays accumulated hits. A minimized window likewise gets one impulse.
        hits = [active and beats[i] != self.previous[i] for i in range(3)]
        self.previous = tuple(beats[:3])
        for side in range(2):
            if hits[side]:
                strength = min(1., max(0., beats[3+side]/64))
                interval = now-self.last_hit[side] if self.last_hit[side] is not None else .7
                self.last_hit[side] = now
                flight = min(.8,max(.13,interval*.88))
                # Aim to land before the next hit; dense percussion makes
                # shorter jumps rather than pinning the sphere at the ceiling.
                self.velocity[side] = max(.5,(5.5*flight-self.height[side]/flight)*(.8+.2*strength))
                self.impact[side] = .8 if self.height[side] < .08 else .2
            # Bounded, small integration steps avoid tunnelling on slow frames.
            remaining = delta
            while remaining > 0:
                dt = min(remaining, 1/120)
                remaining -= dt
                self.velocity[side] -= 11*dt
                self.height[side] += self.velocity[side]*dt
                if self.height[side] >= 1.25:
                    self.height[side] = 1.25
                    self.velocity[side] = min(0., self.velocity[side])
                if self.height[side] <= 0:
                    if self.velocity[side] < -1: self.impact[side] = .6
                    self.height[side], self.velocity[side] = 0., 0.
            self.impact[side] *= math.exp(-delta*13)
        self.shimmer = 1. if hits[2] else self.shimmer*math.exp(-delta*19)


class ScrollState:
    def __init__(self):
        self.position = 0.0
        self.maximum = 0.0
        self.automatic = True
        self.wait = 2.0
        self.at_end = False

    def manual(self, position):
        self.automatic = False
        self.position = max(0.0, min(self.maximum, position))
        self.wait = 0.0
        self.at_end = False

    def tick(self, seconds, hovering=False):
        if not self.automatic or hovering:
            return
        if self.wait > 0:
            self.wait = max(0, self.wait - seconds)
            return
        if self.at_end:
            self.position = 0
            self.wait = 2.0
            self.at_end = False
            return
        self.position = min(self.maximum, self.position + seconds * 20)
        if self.position >= self.maximum and self.maximum:
            self.wait = 5.0
            self.at_end = True


class BouncingSphere:
    """Small shaded checker ball, projected onto the same floor as the grid.

    The mesh is allocated once. Only front-facing cells are shown, and their
    colors come from a cached light palette; no per-frame image allocations.
    """
    def __init__(self, canvas, side):
        self.canvas, self.side = canvas, side
        self.shadows = [canvas.create_oval(0, 0, 1, 1, fill=color, outline='', tags='scene')
                        for color in ('#181712', '#11110e', '#080808')]
        rings, segments = 10, 20
        self.vertices = []
        for ring in range(rings+1):
            latitude = -math.pi/2 + ring*math.pi/rings
            for segment in range(segments):
                longitude = segment*math.tau/segments
                self.vertices.append((math.cos(latitude)*math.sin(longitude),
                                      math.sin(latitude),
                                      math.cos(latitude)*math.cos(longitude)))
        self.faces = []
        for ring in range(rings):
            for segment in range(segments):
                following = (segment+1) % segments
                indices = (ring*segments+segment, ring*segments+following,
                           (ring+1)*segments+following, (ring+1)*segments+segment)
                item = canvas.create_polygon(0, 0, 1, 0, 0, 1, outline='',
                                             state='hidden', tags='scene')
                self.faces.append((indices, (ring//2+segment//2) % 2, item))
        # Low contrast, metallic gold/silver, leaving the foreground text clear.
        bases = ((173, 138, 55), (64, 62, 54)) if side == 0 else ((150, 150, 141), (103, 84, 39))
        self.palette = [[('#%02x%02x%02x' % tuple(min(255, int(v*(.34+i*.026))) for v in base))
                         for i in range(32)] for base in bases]
        self.styles = {}

    def draw(self, t, width, height, horizon, lift, impact, shimmer):
        c, side = self.canvas, self.side
        # Vary distance on the floor: size, travel and footprint all use the
        # same perspective factor instead of making the ball grow arbitrarily.
        depth = (.79 if side == 0 else .59) + .095*math.sin(t*.78+side*2.2)
        cx = width*((.105 if side == 0 else .895) + .025*math.sin(t*.97+side*2.7))
        floor_y = horizon + (height-horizon)*depth*depth
        radius = min(43 if side == 0 else 35, width*.052, height*.13)*depth
        bounce = min(height*.23, 105)*depth*lift
        # Hats add a small, rapidly damped ripple, not another large jump.
        cx += shimmer*math.sin(t*70)*1.8
        rx, ry = radius*(1+.12*impact), radius*(1-.15*impact)
        cy = floor_y-ry-bounce
        footprint = radius*(.9-.25*lift)
        for index, item in enumerate(self.shadows):
            spread = 1-index*.24
            sx, sy = footprint*spread, radius*.20*depth*spread
            c.coords(item, cx-sx, floor_y-sy, cx+sx, floor_y+sy)

        spin, tilt = t*(2.1 if side == 0 else -2.6), .27
        sn, cs, st, ct = math.sin(spin), math.cos(spin), math.sin(tilt), math.cos(tilt)
        rotated = []
        for x,y,z in self.vertices:
            xx, zz = x*cs+z*sn, z*cs-x*sn
            rotated.append((xx, y*ct-zz*st, y*st+zz*ct))
        for indices, checker, item in self.faces:
            face = [rotated[i] for i in indices]
            nx,ny,nz = (sum(vertex[axis] for vertex in face)/4 for axis in range(3))
            if nz <= 0:
                if self.styles.get(item) is not None:
                    c.itemconfigure(item, state='hidden')
                    self.styles[item] = None
                continue
            light = max(0, -nx*.40-ny*.55+nz*.73)
            shade = min(31, int(light*31))
            style = self.palette[checker][shade]
            if self.styles.get(item) != style:
                c.itemconfigure(item, state='normal', fill=style)
                self.styles[item] = style
            c.coords(item, *(coordinate for x,y,z in face for coordinate in (cx+x*rx,cy+y*ry)))


class DemoBackground:
    """Fixed-size scene; items are reused rather than allocated every frame."""
    def __init__(self, canvas):
        self.canvas = canvas
        rng = random.Random(1975)
        self.stars = [(math.sqrt(rng.uniform(.015,.48)),
            rng.uniform(0,math.tau), rng.random(), rng.uniform(.65,1.),
            canvas.create_line(0, 0, 1, 1, fill='#777269', capstyle='round', tags='scene'))
            for _ in range(64)]
        self.star_styles = {}
        self.percussion = PercussionMotion()
        self.grid = [canvas.create_line(0, 0, 0, 0, fill='#332c1d', tags='scene') for _ in range(29)]
        self.waves = [canvas.create_line(0, 0, 0, 0, fill=color, width=1, tags='scene')
                      for color in ('#3e351f', '#6c5628', '#423a28')]
        self.wire = [canvas.create_line(0, 0, 0, 0, fill='#5e5132', tags='scene') for _ in range(24)]
        self.cube_shades = [None, None]
        self.spheres = [BouncingSphere(canvas, side) for side in range(2)]

    def draw(self, t, width, height, pulse, beats=(0,)*6, music_active=False):
        c = self.canvas
        motion = t * BACKGROUND_SPEED
        horizon = height * .66
        self.percussion.update(t, beats, music_active)
        cx,cy = width*.5,height*.46
        for start_radius,angle,phase,speed,item in self.stars:
            # One camera, forward travel along Z: every streak shares the same
            # perspective. Particles already occupy a broad distant plane when
            # they become visible, so they do not all emerge from a central dot.
            dx,dy = math.cos(angle),math.sin(angle)
            edge = min((width-cx if dx>0 else cx)/max(.0001,abs(dx)),
                       (height-cy if dy>0 else cy)/max(.0001,abs(dy)))
            progress = (phase+t*speed) % 1
            depth = 1-(1-start_radius)*progress
            head = start_radius/depth
            tail = start_radius/(depth+(1-start_radius)*speed*.045)
            # Short streaks, not full-screen flashes; fully inside the canvas.
            tail = max(tail,head-min(28,height*.065)/max(1.,edge))
            tail = min(head,tail)
            c.coords(item,cx+dx*edge*tail,cy+dy*edge*tail,cx+dx*edge*head,cy+dy*edge*head)
            fade = min(1.,progress/.10,(1-progress)/.05)
            shade = int(head*fade*15)
            if self.star_styles.get(item) != shade:
                self.star_styles[item] = shade
                color = '#%02x%02x%02x' % (48+shade*8,47+shade*8,43+shade*7)
                c.itemconfigure(item,fill=color,width=1+head*.9)
        # Perspective floor moving toward the viewer, restrained around text.
        for i in range(15):
            bottom = width * (i - 7) / 5 + width / 2
            c.coords(self.grid[i], width/2+(bottom-width/2)*.035, horizon, bottom, height+5)
        for i in range(14):
            z = ((i / 14 + motion * .05) % 1) ** 2
            yy = horizon + (height - horizon) * z
            c.coords(self.grid[15+i], 0, yy, width, yy)
        for layer, item in enumerate(self.waves):
            points = []
            for x in range(0, width + 9, 9):
                y = height*.36 + math.sin(x*.012 + motion*.65 + layer*.35) * (20+pulse*10)
                y += math.sin(x*.006-motion*.4)*22
                points += [x, y]
            c.coords(item, *points)
        # Two cubes travel across the whole stage and reflect at its edges.
        # Camera distance changes their size; projected extents keep even the
        # nearest rotated corners inside the stage when it is resized.
        vertices = [(x, y, z) for x in (-1,1) for y in (-1,1) for z in (-1,1)]
        edges = [(a,b) for a in range(8) for b in range(a+1,8)
                 if sum(vertices[a][j] != vertices[b][j] for j in range(3)) == 1]
        for side in range(2):
            angle = motion*.30 + side*1.5
            near = .5+.5*math.sin(t*(.76 if side == 0 else .59)+side*2.1)
            distance = 5.4-3.5*near
            radius = min(100, width*.12, height*.22)
            projected = []
            for x,y,z in vertices:
                a = x*math.cos(angle)-z*math.sin(angle)
                b = x*math.sin(angle)+z*math.cos(angle)
                yy = y*math.cos(angle*.7)-b*math.sin(angle*.7)
                zz = y*math.sin(angle*.7)+b*math.cos(angle*.7)
                scale = radius/(distance+zz*.17)
                projected.append((a*scale, yy*scale))
            xmin, xmax = min(p[0] for p in projected), max(p[0] for p in projected)
            ymin, ymax = min(p[1] for p in projected), max(p[1] for p in projected)
            # Triangle waves are continuous and reverse direction at contact.
            travel_x = 1-abs((t*(.145 if side == 0 else .119)+side*1.13) % 2-1)
            travel_y = 1-abs((t*(.181 if side == 0 else .153)+.45+side*.83) % 2-1)
            cx = 3-xmin + max(0, width-6-(xmax-xmin))*travel_x
            cy = 3-ymin + max(0, height-6-(ymax-ymin))*travel_y
            shade = int(near*20)
            if self.cube_shades[side] != shade:
                self.cube_shades[side] = shade
                color = '#%02x%02x%02x' % (58+shade*4, 49+shade*3, 31+shade)
                for item in self.wire[side*12:side*12+12]:
                    c.itemconfigure(item, fill=color)
            projected = [(cx+x, cy+y) for x,y in projected]
            for i,(a,b) in enumerate(edges):
                c.coords(self.wire[side*12+i], *projected[a], *projected[b])
        for side,sphere in enumerate(self.spheres):
            sphere.draw(t,width,height,horizon,self.percussion.height[side],
                        self.percussion.impact[side],self.percussion.shimmer)


class CreditsDemo:
    def __init__(self, owner, repositories):
        self.owner, self.repositories = owner, repositories
        self.tr, self.font = owner.tr, owner.ui_font
        self.closed = False
        self.timer = None
        self.scroll = ScrollState()
        self.offset_drawn = 0.0
        self.hovering = False
        self.started = self.last_frame = time.monotonic()
        self.layout_width = self.layout_height = 0
        self.total_height = 1
        self.levels = [0.] * 4
        if getattr(owner, 'credits_music', None) is None:
            owner.credits_music = MusicSession()
        self.session = owner.credits_music
        self.player = self.session.open()

        panel = self.panel = tk.Toplevel(owner.app)
        owner.credits_panel = panel
        panel.withdraw()
        panel.title(APP_NAME + ' — ' + self.tr('credits'))
        panel.configure(bg=BG)
        panel.transient(owner.app)
        center_dialog(panel, owner.app, 890, 780)
        panel.minsize(700, 540)

        self.header = tk.Canvas(panel, height=128, bg=BG, highlightthickness=0)
        self.header.pack(fill='x')
        self.header.bind('<Configure>', self._header)
        self.beam = None
        hintbar = tk.Frame(panel, bg='#202020')
        hintbar.pack(fill='x')
        tk.Label(hintbar, text=self.tr('credits_open_link'), bg='#202020', fg=MUTED,
                 font=(self.font,9), padx=14, pady=7).pack(side='left')
        self.mode = tk.Label(hintbar, text=self.tr('credits_auto'), bg='#202020', fg=GOLD,
                            font=(self.font,9), padx=14)
        self.mode.pack(side='right')

        stage = tk.Frame(panel, bg=BG)
        stage.pack(fill='both', expand=True)
        self.scrollbar = ttk.Scrollbar(stage, orient='vertical', command=self._scrollbar)
        self.scrollbar.pack(side='right', fill='y')
        self.canvas = tk.Canvas(stage, bg=BG, highlightthickness=0, takefocus=True)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.scene = DemoBackground(self.canvas)
        self.canvas.bind('<Configure>', self._layout)
        panel.bind('<MouseWheel>', self._wheel)
        panel.bind('<Button-4>', lambda e: self._manual(self.scroll.position-65))
        panel.bind('<Button-5>', lambda e: self._manual(self.scroll.position+65))
        for key, amount in (('Up',-35),('Down',35),('Prior',-260),('Next',260)):
            panel.bind('<'+key+'>', lambda e,n=amount: self._manual(self.scroll.position+n))
        panel.bind('<Home>', lambda e:self._manual(0))
        panel.bind('<End>', lambda e:self._manual(self.scroll.maximum))

        self._footer()
        panel.protocol('WM_DELETE_WINDOW', self.close)
        panel.bind('<Escape>', lambda _e:self.close())
        panel.bind('<Destroy>', self._destroyed, add='+')
        panel.deiconify()
        panel.grab_set()
        self.canvas.focus_set()
        self._frame()

    def _header(self, event):
        c, w = self.header, event.width
        c.delete('all')
        # Horizontal raster glow, with only the lower edge in strong gold.
        for y in range(0,128,4):
            shade = 20 + int(10*math.sin(y/128*math.pi))
            color = '#%02x%02x%02x' % (shade,shade,shade)
            c.create_rectangle(0,y,w,y+4,fill=color,outline='')
        try:
            if not hasattr(self, 'logo'):
                from PIL import Image, ImageTk
                self.logo = ImageTk.PhotoImage(Image.open(ASSETS/'assets/Retro-Recomp-icon-128.png')
                    .resize((90,90),Image.Resampling.LANCZOS), master=c)
            c.create_image(w/2-235,63,image=self.logo)
        except (OSError, tk.TclError):
            pass
        for bounds,color in wordmark_rectangles(w/2-165,38,4.2):
            c.create_rectangle(*bounds,fill=color,outline='')
        c.create_text(w/2-163,88,text=self.tr('credits_demo_tagline'),anchor='w',
                      fill=MUTED,font=(self.font,9))
        c.create_text(w-18,16,text='v'+__version__,anchor='ne',fill='#777777',font=(self.font,8))
        c.create_line(0,126,w,126,fill='#574925')
        self.beam = c.create_line(0,126,130,126,fill=GOLD,width=2)
        for x,y,size,color in ((w-42,86,10,GOLD),(w-55,99,7,'#8b702e')):
            c.create_rectangle(x,y,x+size,y+size,fill=color,outline='')

    def _footer(self):
        footer = tk.Frame(self.panel,bg='#202020',padx=16,pady=10)
        footer.pack(fill='x')
        playback = tk.Frame(footer,bg='#202020')
        playback.pack(fill='x')
        self.meter = tk.Canvas(playback,width=76,height=38,bg='#202020',highlightthickness=0)
        self.meter.pack(side='left',padx=(0,12))
        self.meter_items = []
        for ch in range(4):
            bars = []
            for step in range(8):
                bars.append(self.meter.create_rectangle(2+ch*18,32-step*4,13+ch*18,34-step*4,
                                                        fill='#39352b',outline=''))
            self.meter_items.append(bars)
        track = tk.Frame(playback,bg='#202020')
        track.pack(side='left',fill='x',expand=True)
        tk.Label(track,text=self.player.title,bg='#202020',fg=WHITE,
                 font=(self.font,11,'bold'),anchor='w').pack(anchor='w')
        self.track_info = tk.Label(track,text=self.tr('credits_audio_starting'),bg='#202020',fg=MUTED,
                                   font=(self.font,8),anchor='w')
        self.track_info.pack(anchor='w')
        self.mute_button = ttk.Button(playback,text=self.tr('credits_sound_on'),command=self._mute)
        self.mute_button.pack(side='right')
        self._mute_text()
        actions = tk.Frame(footer,bg='#202020')
        actions.pack(fill='x',pady=(9,8))
        self.auto_button = ttk.Button(actions,text=self.tr('credits_pause'),command=self._toggle_auto)
        self.auto_button.pack(side='left')
        ttk.Button(actions,text=self.tr('credits_notices'),command=self.owner.show_legal_notices).pack(side='left',padx=8)
        ttk.Button(actions,text=self.tr('close'),command=self.close).pack(side='right')
        bottom = tk.Frame(footer,bg='#202020')
        bottom.pack(fill='x')
        tk.Label(bottom,text=self.tr('credits_manual_hint'),bg='#202020',fg='#939393',
                 wraplength=350,justify='left',font=(self.font,8)).pack(side='left',anchor='s')
        author = tk.Frame(bottom,bg='#202020')
        author.pack(side='right')
        tk.Label(author,text=self.tr('credits_author')+' · Arthur Reboul Salze',bg='#202020',fg=MUTED,
                 font=(self.font,8)).pack(anchor='e')
        link = tk.Label(author,text=self.tr('credits_chiploom'),bg='#202020',fg=GOLD,
                        cursor='hand2',font=(self.font,8,'underline'))
        link.pack(anchor='e',pady=(3,0))
        link.bind('<Button-1>',lambda _e:webbrowser.open_new_tab('https://github.com/ArthurReboulSalze/ChipLoom'))

    def _layout(self, event):
        w,h = event.width,event.height
        if (w,h) == (self.layout_width,self.layout_height): return
        self.layout_width,self.layout_height = w,h
        self.canvas.delete('credit')
        self.offset_drawn = 0
        c = self.canvas
        left,right = max(88,(w-570)/2), min(w-88,(w+570)/2)
        middle = w/2
        y = 28

        def text(label, y, size=10, color=MUTED, bold=False, width=None):
            item = c.create_text(middle,y,text=label,anchor='n',justify='center',
                width=width or right-left-35,fill=color,
                font=(self.font,size,'bold' if bold else 'normal'),tags=('credit',))
            box = c.bbox(item)
            return item, (box[3]-box[1] if box else size*2)

        _, used = text(self.tr('credits_intro'),y,10,width=right-left)
        y += used+26
        for index,(system,repositories) in enumerate(self.repositories):
            top = y
            c.create_line(left,top,right,top,fill='#584b2a',tags='credit')
            c.create_line(left,top,left+44,top,fill=GOLD,width=2,tags='credit')
            c.create_text(left+8,top+15,text=f'{index+1:02d}',anchor='nw',fill=GOLD,
                          font=('Consolas',10),tags='credit')
            _,used = text(system.upper(),y+16,15,WHITE,True)
            y += used+34
            for repository,url,role in repositories:
                item,used = text(repository,y,11,GOLD)
                c.tag_bind(item,'<Enter>',lambda e,i=item:self._hover(True,i))
                c.tag_bind(item,'<Leave>',lambda e,i=item:self._hover(False,i))
                c.tag_bind(item,'<Button-1>',lambda e,address=url:webbrowser.open_new_tab(address))
                y += used+3
                _,used = text(self.tr(role),y,9)
                y += used+13
            y += 5
            c.create_line(left,top,left,y,right,y,right,top,fill='#33302a',tags='credit')
            y += 25
        _,used = text(self.tr('credits_thanks'),y,17,WHITE,True)
        y += used+18
        _,used = text(self.tr('credits_license'),y,9)
        y += used+20
        item,used = text('libxmp-lite  /  miniaudio',y,9,GOLD)
        c.tag_bind(item,'<Button-1>',lambda _e:self.owner.show_legal_notices())
        c.tag_bind(item,'<Enter>',lambda e,i=item:self._hover(True,i))
        c.tag_bind(item,'<Leave>',lambda e,i=item:self._hover(False,i))
        self.total_height = y+used+max(80,h*.35)
        self.scroll.maximum = max(0,self.total_height-h)
        self.scroll.position = min(self.scroll.position,self.scroll.maximum)
        self._position()

    def _hover(self, value, item):
        self.hovering = value
        self.canvas.configure(cursor='hand2' if value else '')
        self.canvas.itemconfigure(item,fill=COLORS['gold_hover'] if value else GOLD)

    def _position(self):
        self.canvas.move('credit',0,self.offset_drawn-self.scroll.position)
        self.offset_drawn = self.scroll.position
        self.scrollbar.set(self.scroll.position/self.total_height,
                           min(1,(self.scroll.position+self.layout_height)/self.total_height))

    def _manual(self, value):
        self.scroll.manual(value)
        self._position()
        self._auto_text()
        return 'break'

    def _wheel(self, event):
        if event.delta:
            # Windows uses 120 units per wheel detent; high-resolution wheels
            # can supply smaller deltas. Linux X11 uses Button-4/5 instead.
            self._manual(self.scroll.position-event.delta/120*65)
        return 'break'

    def _scrollbar(self, action, value, units=None):
        if action == 'moveto':
            self._manual(float(value)*self.total_height)
        else:
            amount = self.layout_height*.8 if units == 'pages' else 35
            self._manual(self.scroll.position+int(value)*amount)

    def _auto_text(self):
        self.auto_button.configure(text=self.tr('credits_pause' if self.scroll.automatic else 'credits_resume'))
        self.mode.configure(text=self.tr('credits_auto' if self.scroll.automatic else 'credits_manual'))

    def _toggle_auto(self):
        self.scroll.automatic = not self.scroll.automatic
        self.scroll.wait = 0
        self._auto_text()

    def _mute_text(self):
        self.mute_button.configure(text=self.tr('credits_sound_off' if self.player.muted else 'credits_sound_on'))

    def _mute(self):
        self.player.muted = not self.player.muted
        self.session.set_muted(self.player.muted)
        self._mute_text()

    def _frame(self):
        if self.closed: return
        now = time.monotonic()
        delta,self.last_frame = min(.1,now-self.last_frame),now
        if self.panel.state() != 'iconic' and self.canvas.winfo_viewable():
            self.scroll.tick(delta,self.hovering)
            self._position()
            values = self.player.values
            pulse = max(values[8:])/32768 if self.player.status == 'playing' and not self.player.muted else 0
            self.scene.draw(now-self.started,max(1,self.layout_width),max(1,self.layout_height),pulse,
                            self.player.beats,self.player.status == 'playing' and not self.player.muted)
            if self.beam:
                width = self.header.winfo_width()
                x = (math.sin((now-self.started)*.35)*.5+.5)*max(1,width-140)
                self.header.coords(self.beam,x,126,x+140,126)
            for channel in range(4):
                target = values[4+channel]/64 if pulse else 0
                self.levels[channel] = max(target,self.levels[channel]-delta*1.8)
                for step,item in enumerate(self.meter_items[channel]):
                    color = (GOLD if step<6 else '#f2d887') if step/8<self.levels[channel] else '#39352b'
                    self.meter.itemconfigure(item,fill=color)
            if self.player.status == 'playing':
                info = self.tr('credits_module_info',pattern=f'{values[1]:02X}',row=f'{values[2]:02X}')
            else:
                info = self.tr('credits_audio_missing' if self.player.status == 'unavailable' else 'credits_audio_starting')
            if self.track_info.cget('text') != info: self.track_info.configure(text=info)
        self.timer = self.panel.after(33,self._frame)

    def _destroyed(self, event):
        if event.widget is self.panel: self._cleanup()

    def _cleanup(self):
        if self.closed: return
        self.closed = True
        if self.timer:
            self.panel.after_cancel(self.timer)
            self.timer = None
        self.player.close()
        if self.owner.credits_panel is self.panel:
            self.owner.credits_panel = None
        self.owner.credits_demo = None

    def close(self):
        if self.closed: return
        self._cleanup()
        self.panel.grab_release()
        self.panel.destroy()
