// Retro-Recomp's copy of the pinned pcenginerecomp runtime/src/pcm.cpp (MIT, licenses/pcenginerecomp.md), made from the file whose SHA-256 is
// retrorecomp/pce_build.PATCHED_ENGINE_FILES. Three small edits, each marked "Retro-Recomp patch": a HuCard has no CD, so the CD audio clock fields
// are not brought up to date after every retired instruction (docs/UPSTREAMS.md, "Our patches of the PC Engine engine"). Nothing else differs.
#include "pce/runtime.hpp"
#include "pce/cdda_pcm.hpp"
#include "pce/audio_dsp.hpp"
#include "pce/checkpoint_audio.hpp"
#include "pce/checkpoint_archive.hpp"
#include <cmath>
#include <type_traits>
#include <algorithm>
#include <limits>

namespace pce {
namespace {
constexpr std::uint64_t master_clock=21477273;
void validate_profile(AudioProfile profile,unsigned rate) {
    if((profile!=AudioProfile::raw && profile!=AudioProfile::filtered) ||
       (rate!=44100 && rate!=48000) || (profile==AudioProfile::raw && rate!=44100))
        throw Fault("unsupported audio profile or output rate");
}
void devices(Bus& bus,std::uint64_t ticks,bool psg=false) {
    if(bus.adpcm.enabled)bus.adpcm.advance_to(ticks,&bus.cd);
    else if(bus.cd.scsi.enabled)bus.cd.advance_to(ticks); // Retro-Recomp patch 1: CdControl::advance_to returns at once without a CD transport
    if(psg)bus.psg.advance_to(ticks);
}
void silent_source_to(CdAudio& audio,std::uint64_t ticks) {
    // Advance the global rational phase without polling disabled hardware.
    // Division before multiplication also keeps the full uint64 tick range
    // representable; the remainder products are bounded by the clock rate.
    const auto count=(ticks/master_clock)*44100+(ticks%master_clock)*44100/master_clock;
    const auto edge=[](std::uint64_t frame) {
        const auto whole=(frame/44100)*master_clock;
        const auto part=((frame%44100)*master_clock+44099)/44100;
        // A disabled source need not schedule an event outside the guest
        // timestamp domain. Its final representable edge/count remain exact.
        if(whole>std::numeric_limits<std::uint64_t>::max()-part)return std::uint64_t{0};
        return whole+part;
    };
    if(count!=audio.sample_frames) {audio.sample_raw={};audio.sample_held={};audio.sample_valid=true;}
    audio.sample_frames=count;audio.sample_ticks=edge(count);
    audio.sample_next_tick=edge(count+1);
    audio.sample_remainder=static_cast<unsigned>(((count+1)%44100*(master_clock%44100)+44099)%44100);
    audio.sample_clock_ticks=ticks;
}

}
// Media caching and legacy presentation compatibility stay opaque. The
// canonical guest cursor and readable DAC are value state in CdAudio.
class CddaStreamState {
public:
    explicit CddaStreamState(AudioProfile profile,unsigned rate,AudioTiming timing):profile(profile),timing(timing),resampler(rate) {}
    AudioProfile profile;
    AudioTiming timing;
    AudioProcessingStats processing;
    PsgPresentationFilter psg_filter;
    AdpcmPresentationFilter adpcm_filter;
    StereoResampler resampler;
    CddaPcmCache cache;
    CdAudio::Cursor legacy_cursor;
};
AudioOutput::AudioOutput()=default;
AudioOutput::~AudioOutput()=default;
AudioOutput::AudioOutput(AudioOutput&&) noexcept=default;
AudioOutput& AudioOutput::operator=(AudioOutput&&) noexcept=default;
void AudioOutput::enable(AudioProfile profile,unsigned output_rate,AudioTiming timing) {
    if(enabled || master_ticks || frames)throw Fault("audio output must be enabled before guest execution");
    validate_profile(profile,output_rate);
    if(timing!=AudioTiming::gear && timing!=AudioTiming::legacy)throw Fault("unsupported audio timing");
    cd_cache_=std::make_unique<CddaStreamState>(profile,output_rate,timing);enabled=true;
    // ceil(n*M/R) is floor((n*M+R-1)/R). The phase must retain
    // that R-1 offset, including exact rational-period boundaries.
    if(timing==AudioTiming::gear) {next_tick_=488;remainder_=572;}
    cd_cache_->processing.latency_source_frames=cd_cache_->resampler.latency();
}
AudioProfile AudioOutput::profile() const {return cd_cache_ ? cd_cache_->profile:AudioProfile::raw;}
AudioTiming AudioOutput::timing() const {return cd_cache_ ? cd_cache_->timing:AudioTiming::gear;}
unsigned AudioOutput::output_rate() const {return cd_cache_ ? cd_cache_->resampler.output_rate():44100;}
AudioProcessingStats AudioOutput::processing_stats() const {return cd_cache_ ? cd_cache_->processing:AudioProcessingStats{};}
void AudioOutput::reset_adpcm_filter() {if(cd_cache_)cd_cache_->adpcm_filter.reset();}
void AudioOutput::append(std::array<std::int16_t,2> sample) {
    if(count_==capacity){begin_=(begin_+1)%capacity;--count_;++discarded_frames;}
    queue_[(begin_+count_)%capacity]=sample;++count_;
    for(auto value:sample) {
        const auto u=static_cast<std::uint16_t>(value);
        for(unsigned shift:{0u,8u}){pcm_hash^=(u>>shift)&255;pcm_hash*=1099511628211ULL;}
        peak=std::max(peak,static_cast<unsigned>(value<0 ? -int(value):int(value)));
    }
    if(sample[0] || sample[1])++mixed_nonzero;
    ++frames;
}
void CdAudio::Cursor::observe(const CdControl& cd) {
    const auto& audio=cd.audio;
    // RST can leave an already naturally stopped drive's observed command,
    // state and sector counters unchanged. It still cancels the terminal
    // token immediately, including between adjacent output sample edges.
    if(cd.reset&2) {
        active=finished=tail_pending=false;
        frame=0;
    }
    const bool same_source=!source.owner_before(cd.provider) && !cd.provider.owner_before(source);
    if(same_source && was_enabled==cd.audio_enabled &&
       last_state==audio.state && commands_seen==audio.commands &&
       sectors_seen==audio.sectors_played && seek_seen==audio.seek_deadline) return;
    const auto reset=[&] {active=finished=tail_pending=false;frame=0;};
    if(!same_source || !cd.audio_enabled) reset();
    if(audio.seek_deadline || audio.state==1) reset();
    else if(audio.state==3) {
        // A rounded natural stop may precede the last 44.1 kHz source sample
        // by one output edge. Deliver only that exact terminal frame once.
        // An explicit stop/READ/reset does not acquire this completion token.
        const bool natural=last_state==0 && audio.sectors_played>sectors_seen &&
                           (audio.commands==commands_seen || cd.scsi.command[0]==0xdd);
        if(natural) {
            tail_pending=active && lba>=audio.stop_lba && frame==587;
            if(!tail_pending) reset();
        } else if(last_state!=3 || (audio.commands!=commands_seen && cd.scsi.command[0]!=0xdd)) reset();
    } else if(audio.state==2) {
        // Pause and its resume delay hold the PCM cursor, rather than replaying
        // the beginning of the guest drive's current sector after resumption.
        tail_pending=false;
    } else if(audio.state==0 && finished && audio.commands!=commands_seen &&
              cd.scsi.command[0]==0xd9 && cd.scsi.command[1]) reset();
    source=cd.provider;was_enabled=cd.audio_enabled;
    last_state=audio.state;commands_seen=audio.commands;
    sectors_seen=audio.sectors_played;seek_seen=audio.seek_deadline;
}
std::array<std::int16_t,2> CdAudio::Cursor::sample(CdControl& cd,CddaPcmCache& cache,bool& valid) {
    observe(cd);valid=true;
    const auto& audio=cd.audio;
    if(!cd.audio_enabled || (cd.reset&2) || audio.seek_deadline || audio.playback_deadline ||
       (audio.state!=0 && !tail_pending)) return {};
    if(audio.state==0 && !audio.sector_deadline) return {};
    if(finished) return {};
    if(!active) {lba=audio.current_lba;frame=0;active=true;}
    // An admitted D9 can move the end behind an already playing sector. The
    // drive still emits that sector's remaining samples before LOOP/IRQ/STOP;
    // changing the end is not an immediate sample gate.
    // A control-only transport can model seeks without media. Its source DAC
    // is explicitly unavailable until a provider is attached; observing that
    // value via the latch or enabled PCM is an error, never invented silence.
    std::array<std::int16_t,2> result{};
    if(cd.provider) result=cache.sample(cd.provider,lba,frame);
    else valid=false;
    if(++frame==588) {
        frame=0;
        if(lba>=audio.stop_lba) {
            if(audio.stop_mode==1) lba=audio.start_lba;
            else {active=false;finished=true;}
        } else ++lba;
    }
    tail_pending=false;
    return result;
}
void AudioOutput::advance_to(Bus& bus,std::uint64_t ticks) {
    auto& audio=bus.cd.audio;
    if(ticks<audio.sample_clock_ticks)throw Fault("CPU/CD sample clock regression");
    if(!enabled && !bus.cd.audio_enabled) {
        devices(bus,ticks);
        if(bus.cd.enabled)silent_source_to(audio,ticks);
        return;
    }
    if(enabled && ticks<master_ticks)throw Fault("CPU/audio output clock regression");
    if(!cd_cache_)cd_cache_=std::make_unique<CddaStreamState>(AudioProfile::raw,44100,AudioTiming::gear);
    unsigned source_budget=0,output_budget=0;
    for(;;) {
        const auto source_tick=bus.cd.audio_enabled && audio.sample_next_tick ? audio.sample_next_tick:
            std::numeric_limits<std::uint64_t>::max();
        const auto output_tick=enabled ? next_tick_:std::numeric_limits<std::uint64_t>::max();
        const auto next=std::min(source_tick,output_tick);
        if(next>ticks || next==std::numeric_limits<std::uint64_t>::max())break;
        const bool source_edge=next==source_tick,output_edge=next==output_tick;
        if((source_edge && ++source_budget>441000) || (output_edge && ++output_budget>441000))
            throw Fault("audio source/output advance exceeds ten-second work bound");
        devices(bus,next,output_edge);
        if(source_edge) {
            audio.sample_raw=audio.source_cursor.sample(bus.cd,cd_cache_->cache,audio.sample_valid);
            const auto gain=bus.cd.fader_gain(false);
            for(unsigned channel=0;channel<2;++channel)
                audio.sample_held[channel]=static_cast<std::int16_t>(audio.sample_raw[channel]*gain);
            audio.sample_ticks=next;++audio.sample_frames;
            auto delta=master_clock/rate;
            audio.sample_remainder+=master_clock%rate;
            if(audio.sample_remainder>=rate){audio.sample_remainder-=rate;++delta;}
            audio.sample_next_tick=audio.sample_next_tick>std::numeric_limits<std::uint64_t>::max()-delta ?
                0:audio.sample_next_tick+delta;
        }
        if(!output_edge)continue;
        const auto psg=timing()==AudioTiming::gear ? bus.psg.held_pcm():bus.psg.sample_pcm();
        const auto adpcm=bus.adpcm.enabled && bus.adpcm.playing && !(bus.adpcm.control&128) ? bus.adpcm.sample_pcm():0;
        bool cd_valid=true;
        const auto cd=timing()==AudioTiming::legacy ? cd_cache_->legacy_cursor.sample(bus.cd,cd_cache_->cache,cd_valid):
            (bus.cd.audio_enabled ? audio.sample_raw:std::array<std::int16_t,2>{});
        if(!cd_valid || (timing()==AudioTiming::gear && bus.cd.audio_enabled && !audio.sample_valid))
            throw Fault("CD audio playback requires a sector provider");
        if(psg[0] || psg[1])++psg_nonzero;
        if(adpcm)++adpcm_nonzero;
        if(cd[0] || cd[1])++cdda_nonzero;
        const auto adpcm_gain=bus.cd.fader_gain(true),cd_gain=bus.cd.fader_gain(false);
        std::array<std::int16_t,2> mixed{};
        for(unsigned channel=0;channel<2;++channel) {
            // Fixed equal source gains supply headroom. Gain is presentation
            // policy, not a claim about the console's analog output circuit.
            const auto sum=static_cast<std::int32_t>(psg[channel])+static_cast<std::int32_t>(adpcm*adpcm_gain)
                +static_cast<std::int32_t>(cd[channel]*cd_gain);
            mixed[channel]=static_cast<std::int16_t>(std::clamp(sum/3,-32768,32767));
        }
        if(cd_cache_->profile==AudioProfile::raw)append(mixed);
        else {
            auto& state=*cd_cache_;
            auto& raw=state.processing;
            ++raw.source_frames;
            if(mixed[0] || mixed[1])++raw.raw_mixed_nonzero;
            for(const auto value:mixed) {
                const auto u=static_cast<std::uint16_t>(value);
                for(unsigned shift:{0u,8u}) {raw.raw_pcm_hash^=(u>>shift)&255;raw.raw_pcm_hash*=1099511628211ULL;}
                raw.raw_peak=std::max(raw.raw_peak,static_cast<unsigned>(value<0 ? -int(value):int(value)));
            }
            // Preserve the guest source clocks and the raw reference above.
            // Filters consume the unclipped PSG half-sum and held ADPCM DAC;
            // stopping playback retains its analog-style filter tail.
            const auto filtered_psg=state.psg_filter.process(timing()==AudioTiming::gear ? bus.psg.held_sum():bus.psg.sample_sum());
            if(bus.adpcm.control&128)state.adpcm_filter.reset();
            const auto filtered_adpcm=bus.adpcm.enabled ? state.adpcm_filter.process(
                bus.adpcm.decoder_output,static_cast<float>(adpcm_gain)):0;
            for(unsigned channel=0;channel<2;++channel) {
                const auto sum=static_cast<std::int32_t>(filtered_psg[channel])+filtered_adpcm+
                    static_cast<std::int32_t>(cd[channel]*cd_gain);
                mixed[channel]=static_cast<std::int16_t>(std::clamp(sum/3,-32768,32767));
            }
            const auto output=state.resampler.push(mixed);
            for(unsigned i=0;i<output.count;++i)append(output.samples[i]);
        }
        auto delta=master_clock/rate;
        remainder_+=master_clock%rate;
        if(remainder_>=rate){remainder_-=rate;++delta;}
        if(next_tick_>std::numeric_limits<std::uint64_t>::max()-delta)throw Fault("audio output clock overflow");
        next_tick_+=delta;
    }
    devices(bus,ticks);
    // Retro-Recomp patch 2: a HuCard has no CD, ADPCM or CD audio. Nothing reads the CD audio phase fields, the cursor or the sample clock,
    // yet they were brought up to date after every retired instruction (about a fifth of a frame). They are brought up to date by
    // settle_silent_cd_source below, which the host calls before it reads them (a checkpoint); the result is the same.
    if(!bus.cd.enabled && !bus.cd.scsi.enabled && !bus.cd.audio_enabled && !bus.adpcm.enabled && timing()!=AudioTiming::legacy) {
        if(enabled)master_ticks=ticks;
        return;
    }
    if(!bus.cd.audio_enabled)silent_source_to(audio,ticks);
    audio.source_cursor.observe(bus.cd);
    if(enabled && timing()==AudioTiming::legacy)cd_cache_->legacy_cursor.observe(bus.cd);
    audio.sample_clock_ticks=ticks;
    if(enabled)master_ticks=ticks;
}
// Retro-Recomp patch 3: what advance_to leaves undone on a HuCard (patch 2), done at the last tick advance_to saw. The same functions, in the same
// order, as the end of advance_to: the fields end up exactly as if every instruction had updated them.
void settle_silent_cd_source(Bus& bus) {
    if(bus.cd.enabled || bus.cd.scsi.enabled || bus.cd.audio_enabled || bus.adpcm.enabled || !bus.pcm.enabled) return;
    auto& audio=bus.cd.audio;
    const auto ticks=bus.pcm.master_ticks;
    if(ticks<audio.sample_clock_ticks)throw Fault("CPU/CD sample clock regression");
    silent_source_to(audio,ticks);
    audio.source_cursor.observe(bus.cd);
    audio.sample_clock_ticks=ticks;
}
std::vector<std::int16_t> AudioOutput::drain() {
    std::vector<std::int16_t> samples; samples.reserve(count_*2);
    while(count_) {
        const auto value=queue_[begin_];samples.push_back(value[0]);samples.push_back(value[1]);
        begin_=(begin_+1)%capacity;--count_;
    }
    return samples;
}
void Bus::enable_audio_output(AudioProfile profile,unsigned output_rate,AudioTiming timing) {
    validate_profile(profile,output_rate);
    if(timing!=AudioTiming::gear && timing!=AudioTiming::legacy)throw Fault("unsupported audio timing");
    if(psg.clock_ticks || adpcm.master_ticks || cd.scsi.master_ticks || cd.audio.sample_clock_ticks)
        throw Fault("enable audio output before guest clocks advance");
    if(!psg.enabled)enable_psg();
    pcm.enable(profile,output_rate,timing);psg.synthesis_enabled=true;
}

// Checkpoint fields are intentionally listed here rather than exposing opaque
// presentation implementation details to the machine/host archive layers.
struct AudioCheckpointAccess {
    template<class A> static constexpr bool reading=std::is_same_v<A,checkpoint::Reader>;
    template<class A,class T> static void binding(A& ar,T& source,const std::shared_ptr<SectorProvider>& provider) {
        std::uint8_t token=0;
        if constexpr(!reading<A>) {
            const std::weak_ptr<SectorProvider> empty;
            if(source.owner_before(empty) || empty.owner_before(source)) {
                if(!provider || source.owner_before(provider) || provider.owner_before(source))
                    throw checkpoint::ArchiveError("checkpoint cannot bind a stale or foreign CD audio source");
                token=1;
            }
        }
        ar(token);
        if constexpr(reading<A>) {
            if(token>1 || (token && !provider)) throw checkpoint::ArchiveError("invalid checkpoint CD audio source binding");
            if(token) source=provider; else source.reset();
        }
    }
    template<class A,class T> static void cursor(A& ar,T& v,const std::shared_ptr<SectorProvider>& provider) {
        binding(ar,v.source,provider);
        ar(v.lba,v.frame,v.last_state,v.commands_seen,v.sectors_seen,v.seek_seen,
           v.active,v.finished,v.tail_pending,v.was_enabled);
    }
    template<class A,class T> static void origin(A& ar,T& v) {
        ar(v.valid,v.pc,v.ticks,v.mpr,v.fetch,v.readable);
    }
    template<class A,class T> static void cd(A& ar,T& v) {
        bool attached=bool(v.provider);ar(attached);
        if constexpr(reading<A>) {
            if(attached!=bool(v.provider)) throw checkpoint::ArchiveError("checkpoint CD provider configuration mismatch");
        }
        ar(v.enabled,v.bram_unlocked,v.ack,v.interrupt_enable,v.interrupt_active,v.reset,
           v.reads,v.writes,v.toc_replies,v.data_bytes_acked,v.read_commands,v.sectors_read,
           v.read_retries,v.read_errors,v.pending_sense.key,v.pending_sense.asc,
           v.pending_sense.ascq,v.pending_sense.fru,v.pending_sense.failed_lba,
           v.sense_commands,v.sense_errors,v.audio_enabled);
        auto policy=static_cast<std::uint8_t>(v.unknown_policy);
        ar(policy);
        if(policy>static_cast<std::uint8_t>(CdUnknownPolicy::nec_invalid))
            throw checkpoint::ArchiveError("invalid checkpoint CD unknown-command policy");
        if constexpr(reading<A>)v.unknown_policy=static_cast<CdUnknownPolicy>(policy);
        auto drive_timing=static_cast<std::uint8_t>(v.timing_profile);
        ar(drive_timing);
        if(drive_timing>static_cast<std::uint8_t>(CdTimingProfile::gear_distance))
            throw checkpoint::ArchiveError("invalid checkpoint CD timing profile");
        if constexpr(reading<A>)v.timing_profile=static_cast<CdTimingProfile>(drive_timing);
        auto subchannel_profile=static_cast<std::uint8_t>(v.subchannel_profile);
        ar(subchannel_profile);
        if(subchannel_profile>static_cast<std::uint8_t>(CdSubchannelProfile::captured_q))
            throw checkpoint::ArchiveError("invalid checkpoint CD subchannel profile");
        if constexpr(reading<A>)v.subchannel_profile=static_cast<CdSubchannelProfile>(subchannel_profile);
        auto& q=v.subchannel;
        ar(q.last,q.position,q.last_valid,q.position_valid,q.sampled_lba,q.samples,q.missing,q.crc_errors);
        ar(v.unknown_commands,v.invalid_commands,v.unknown_opcodes,v.last_unknown_command,v.last_unknown_size);
        origin(ar,v.pending_origin);origin(ar,v.last_unknown_origin);
        auto& s=v.scsi;
        ar(s.enabled,s.status_pending,s.phase,s.signals,s.latch,s.data,s.master_ticks,
           s.deadline,s.auto_ack_deadline,s.event,s.command,s.last_command,s.response,
           s.read_active,s.load_lba,s.current_lba,s.load_remaining,s.load_deadline,
           s.response_size,s.response_index,s.command_size,s.last_command_size);
        auto& a=v.audio;
        ar(a.state,a.stop_mode,a.start_lba,a.current_lba,a.stop_lba,a.seek_start_lba,
           a.deadline,a.seek_deadline,a.sector_deadline,a.playback_deadline,a.sectors_played,
           a.commands,a.sector_fraction,a.fader,a.fade_start,a.fade_duration);
        cursor(ar,a.source_cursor,v.provider);
        ar(a.sample_raw,a.sample_held,a.sample_valid,a.sample_right,a.sample_latch,
           a.sample_last_latch,a.sample_frames,a.sample_ticks,a.sample_clock_ticks,
           a.sample_next_tick,a.sample_remainder);
        bool has_toc=v.toc.has_value();ar(has_toc);
        if constexpr(reading<A>) {if(has_toc) v.toc.emplace();else v.toc.reset();}
        if(has_toc) {
            auto& toc=*v.toc;
            ar(toc.track_count,toc.leadout_lba);ar.string(toc.image_sha256,64);
            for(auto& track:toc.tracks) ar(track.index1_lba,track.type);
        }
    }
    template<class A,class T> static void psg(A& ar,T& v) {
        ar(v.enabled,v.synthesis_enabled,v.centered_dac,v.clock_ticks,v.master_remainder,
           v.selected,v.main_volume,v.lfo_frequency,v.lfo_control,v.writes);
        for(auto& c:v.channels)
            ar(c.frequency,c.control,c.balance,c.wave_index,c.wave,c.dda,c.noise,
               c.waveform,c.wave_remaining,c.noise_remaining,c.noise_lfsr,c.held_output);
    }
    template<class A,class T> static void adpcm(A& ar,T& v) {
        ar(v.enabled,v.playing,v.play_pending,v.nibble,v.end_irq,v.half_irq,v.ram,
           v.control,v.dma,v.sample_rate,v.read_latch,v.write_latch,v.last_nibble,
           v.address,v.read_address,v.write_address,v.length,v.master_ticks,
           v.read_deadline,v.write_deadline,v.dma_deadline,v.sample_phase,v.samples,
           v.reads,v.writes,v.dma_bytes,v.decoder_output,v.decoder_index);
    }
    template<class A,class T> static void pcm(A& ar,T& v,const std::shared_ptr<SectorProvider>& provider) {
        ar(v.enabled,v.master_ticks,v.frames,v.discarded_frames,v.psg_nonzero,
           v.adpcm_nonzero,v.cdda_nonzero,v.mixed_nonzero,v.pcm_hash,v.peak,v.queue_);
        std::uint32_t begin=static_cast<std::uint32_t>(v.begin_),count=static_cast<std::uint32_t>(v.count_);
        ar(begin,count,v.next_tick_,v.remainder_);
        if constexpr(reading<A>) {
            if(begin>=AudioOutput::capacity || count>AudioOutput::capacity)
                throw checkpoint::ArchiveError("checkpoint PCM ring exceeds bounds");
            v.begin_=begin;v.count_=count;
        }
        bool present=bool(v.cd_cache_);ar(present);
        if(!present) {if constexpr(reading<A>)v.cd_cache_.reset();return;}
        std::uint32_t profile=0,timing=0,rate=44100;
        if constexpr(!reading<A>) {
            profile=static_cast<std::uint32_t>(v.cd_cache_->profile);
            timing=static_cast<std::uint32_t>(v.cd_cache_->timing);
            rate=v.cd_cache_->resampler.output_rate();
        }
        ar(profile,timing,rate);
        if(profile>1 || timing>1 || (rate!=44100 && rate!=48000) || (profile==0 && rate!=44100))
            throw checkpoint::ArchiveError("unsupported checkpoint audio presentation profile");
        if constexpr(reading<A>) v.cd_cache_=std::make_unique<CddaStreamState>(
            static_cast<AudioProfile>(profile),rate,static_cast<AudioTiming>(timing));
        auto& state=*v.cd_cache_;
        auto& p=state.processing;
        ar(p.source_frames,p.raw_pcm_hash,p.raw_mixed_nonzero,p.raw_peak,p.latency_source_frames);
        ar(state.psg_filter.previous_input_,state.psg_filter.previous_output_,
           state.adpcm_filter.previous_input_,state.adpcm_filter.previous_output_,
           state.adpcm_filter.lowpass_,state.adpcm_filter.gain_);
        auto& r=state.resampler;
        ar(r.write_,r.remainder_,r.input_frames_,r.output_frames_,r.history_);
        auto& cache=state.cache;
        binding(ar,cache.source_,provider);ar(cache.samples_,cache.lba_,cache.valid_);
        cursor(ar,state.legacy_cursor,provider);
    }
    static void validate_cursor(const CdAudio::Cursor& cursor) {
        if(cursor.frame>=588 || cursor.last_state>3 || (cursor.active && cursor.finished))
            throw checkpoint::ArchiveError("checkpoint CD audio cursor exceeds bounds");
    }
    static void validate_pcm(const AudioOutput& v) {
        if(v.begin_>=AudioOutput::capacity || v.count_>AudioOutput::capacity ||
           v.count_>v.frames || v.discarded_frames>v.frames || v.remainder_>=44100 ||
           v.peak>32768 || v.mixed_nonzero>v.frames ||
           (v.enabled && (!v.cd_cache_ || v.next_tick_<=v.master_ticks)))
            throw checkpoint::ArchiveError("checkpoint PCM state exceeds bounds");
        if(!v.cd_cache_)return;
        const auto& state=*v.cd_cache_;
        validate_profile(state.profile,state.resampler.output_rate());
        if(state.timing!=AudioTiming::gear && state.timing!=AudioTiming::legacy)
            throw checkpoint::ArchiveError("unsupported checkpoint audio timing");
        const auto finite=[](float f) {return std::isfinite(f) && std::abs(f)<=1.0e9f;};
        for(auto f:state.psg_filter.previous_input_)if(!finite(f))throw checkpoint::ArchiveError("invalid checkpoint PSG filter state");
        for(auto f:state.psg_filter.previous_output_)if(!finite(f))throw checkpoint::ArchiveError("invalid checkpoint PSG filter state");
        const auto& a=state.adpcm_filter;
        if(!finite(a.previous_input_) || !finite(a.previous_output_) || !finite(a.lowpass_) ||
           !std::isfinite(a.gain_) || a.gain_<0 || a.gain_>1)
            throw checkpoint::ArchiveError("invalid checkpoint ADPCM filter state");
        const auto& r=state.resampler;
        if(r.write_>=StereoResampler::taps || r.remainder_>=147)
            throw checkpoint::ArchiveError("checkpoint resampler phase exceeds bounds");
        const auto& p=state.processing;
        if(p.raw_peak>32768 || p.raw_mixed_nonzero>p.source_frames || p.latency_source_frames!=r.latency())
            throw checkpoint::ArchiveError("checkpoint audio processing state exceeds bounds");
        // Rational counts use division before multiplication to avoid overflow
        // while rejecting corrupt counters that could conceal a phase reset.
        const auto whole=r.input_frames_/147,tail=r.input_frames_%147;
        if(r.output_rate_==44100) {
            if(r.input_frames_!=r.output_frames_ || r.remainder_ || r.write_)
                throw checkpoint::ArchiveError("checkpoint passthrough resampler counters disagree");
        } else if(whole>UINT64_MAX/160 || whole*160>UINT64_MAX-tail*160/147 ||
                  r.output_frames_!=whole*160+tail*160/147 || r.remainder_!=tail*160%147 ||
                  r.write_!=r.input_frames_%StereoResampler::taps)
            throw checkpoint::ArchiveError("checkpoint FIR resampler counters disagree");
        if(state.profile==AudioProfile::filtered && (p.source_frames!=r.input_frames_ || v.frames!=r.output_frames_))
            throw checkpoint::ArchiveError("checkpoint filtered output counters disagree");
        validate_cursor(state.legacy_cursor);
    }
};

namespace checkpoint {
namespace {
bool same_toc(const CdToc& a,const CdToc& b) {
    if(a.track_count!=b.track_count || a.leadout_lba!=b.leadout_lba || a.image_sha256!=b.image_sha256)return false;
    for(unsigned i=0;i<a.track_count;++i)
        if(a.tracks[i].index1_lba!=b.tracks[i].index1_lba || a.tracks[i].type!=b.tracks[i].type)return false;
    return true;
}
}
void validate_audio(const Bus& bus) {
    const auto& p=bus.psg;
    if(p.master_remainder>=6 || p.selected>7)throw ArchiveError("checkpoint PSG state exceeds bounds");
    for(const auto& c:p.channels) {
        if(c.frequency>4095 || c.wave_index>=32 || c.wave>31 || c.dda>31 ||
           c.noise_lfsr>0x3ffff || c.wave_remaining>4096*256 || c.noise_remaining>1984)
            throw ArchiveError("checkpoint PSG channel exceeds bounds");
        for(auto sample:c.waveform)if(sample>31)throw ArchiveError("checkpoint PSG waveform exceeds bounds");
    }
    const auto& a=bus.adpcm;
    constexpr auto maximum_adpcm_phase=(21477273ULL*65536*16+16050)/32100+65535;
    if(a.decoder_output>4095 || a.decoder_index>48 || a.last_nibble>15 || a.length>0x1ffff ||
       a.sample_phase>maximum_adpcm_phase)
        throw ArchiveError("checkpoint ADPCM state exceeds bounds");
    for(auto time:{a.read_deadline,a.write_deadline,a.dma_deadline})
        if(time && time<=a.master_ticks)throw ArchiveError("checkpoint ADPCM event is not in the future");
    const auto& cd=bus.cd;const auto& s=cd.scsi;const auto& audio=cd.audio;
    const auto& q=cd.subchannel;
    const auto zero=[](const auto& packet) {return std::all_of(packet.begin(),packet.end(),[](auto value){return value==0;});};
    if(static_cast<std::uint8_t>(cd.subchannel_profile)>static_cast<std::uint8_t>(CdSubchannelProfile::captured_q) ||
       q.missing>q.samples || q.crc_errors>q.samples-q.missing || bool(q.samples)!=q.sampled_lba.has_value() ||
       (q.sampled_lba && (!cd.toc || *q.sampled_lba>=cd.toc->leadout_lba)) ||
       q.last_valid!=(q.samples-q.missing-q.crc_errors!=0) ||
       (q.last_valid ? !cd_subq_crc_valid(q.last):!zero(q.last)) ||
       (q.position_valid ? (!q.last_valid || (q.position[0]&15)!=1 || !cd_subq_crc_valid(q.position)):!zero(q.position)) ||
       (q.last_valid && (q.last[0]&15)==1 && (!q.position_valid || q.last!=q.position)) ||
       (cd.subchannel_profile==CdSubchannelProfile::synthesized && q.samples) ||
       (cd.subchannel_profile==CdSubchannelProfile::captured_q &&
        (!cd.enabled || !s.enabled || !cd.provider || !cd.provider->has_subchannel())))
        throw ArchiveError("checkpoint captured Q state or media configuration is invalid");
    if((s.phase!=0 && s.phase!=3 && s.phase!=4 && s.phase!=6 && s.phase!=7 && s.phase!=8) ||
       s.event>7 || s.command_size>s.command.size() || s.last_command_size>s.last_command.size() ||
       s.response_size>s.response.size() || s.response_index>s.response_size || s.load_remaining>256 ||
       s.load_lba>0x1fffff || cd.last_unknown_size>cd.last_unknown_command.size() ||
       cd.pending_sense.key>15 || cd.reset>15 || cd.interrupt_enable>127 ||
       static_cast<std::uint8_t>(cd.unknown_policy)>static_cast<std::uint8_t>(CdUnknownPolicy::nec_invalid) ||
       static_cast<std::uint8_t>(cd.timing_profile)>static_cast<std::uint8_t>(CdTimingProfile::gear_distance) ||
       cd.pending_origin.readable>127 || cd.last_unknown_origin.readable>127)
        throw ArchiveError("checkpoint CD transport state exceeds bounds");
    if(bool(s.event)!=bool(s.deadline))throw ArchiveError("checkpoint CD event/deadline mismatch");
    for(auto time:{s.deadline,s.auto_ack_deadline,s.load_deadline})
        if(time && time<=s.master_ticks)throw ArchiveError("checkpoint CD event is not in the future");
    if(audio.state>3 || audio.stop_mode>2 || audio.sector_fraction>=75 || audio.sample_remainder>=44100 ||
       audio.sample_last_latch>audio.sample_clock_ticks || audio.sample_ticks>audio.sample_clock_ticks ||
       (audio.sample_next_tick && audio.sample_next_tick<=audio.sample_clock_ticks) ||
       ((audio.fader&8) && audio.fade_start>s.master_ticks))
        throw ArchiveError("checkpoint CD audio state exceeds bounds");
    std::uint64_t deadline=0;
    for(auto time:{audio.seek_deadline,audio.sector_deadline,audio.playback_deadline})
        if(time) {
            if(time<=s.master_ticks)throw ArchiveError("checkpoint CD audio event is not in the future");
            if(!deadline || time<deadline)deadline=time;
        }
    if(audio.deadline!=deadline)throw ArchiveError("checkpoint CD audio deadlines disagree");
    AudioCheckpointAccess::validate_cursor(audio.source_cursor);
    if(cd.toc)cd.toc->validate();
    if(cd.provider && (!cd.toc || !same_toc(*cd.toc,cd.provider->toc())))
        throw ArchiveError("checkpoint CD provider/TOC mismatch");
    AudioCheckpointAccess::validate_pcm(bus.pcm);
}
void validate_audio_configuration(const Bus& decoded,const Bus& configured) {
    const auto& a=decoded.cd;const auto& b=configured.cd;
    if(decoded.psg.enabled!=configured.psg.enabled ||
       decoded.psg.synthesis_enabled!=configured.psg.synthesis_enabled ||
       decoded.psg.centered_dac!=configured.psg.centered_dac ||
       decoded.adpcm.enabled!=configured.adpcm.enabled || a.enabled!=b.enabled ||
       a.scsi.enabled!=b.scsi.enabled || a.audio_enabled!=b.audio_enabled ||
       a.unknown_policy!=b.unknown_policy || a.timing_profile!=b.timing_profile ||
       a.subchannel_profile!=b.subchannel_profile || bool(a.provider)!=bool(b.provider) ||
       bool(a.toc)!=bool(b.toc) || (a.toc && !same_toc(*a.toc,*b.toc)) ||
       decoded.pcm.enabled!=configured.pcm.enabled || decoded.pcm.profile()!=configured.pcm.profile() ||
       decoded.pcm.output_rate()!=configured.pcm.output_rate() || decoded.pcm.timing()!=configured.pcm.timing())
        throw ArchiveError("checkpoint audio/CD configuration mismatch");
}
void write_audio(Writer& ar,const Bus& bus) {
    validate_audio(bus);
    AudioCheckpointAccess::cd(ar,bus.cd);AudioCheckpointAccess::psg(ar,bus.psg);
    AudioCheckpointAccess::adpcm(ar,bus.adpcm);AudioCheckpointAccess::pcm(ar,bus.pcm,bus.cd.provider);
}
// Retro-Recomp patch 7: the CD drive and the ADPCM unit, written as the checkpoint writes them and nothing else. A disc machine's multiplayer digest hashes
// them (native/pce_snapshot.cpp): they decide the guest's future (sectors, interrupts, the ADPCM end flags), and the engine's own lists stay the one place that
// names the fields, so a field added at a new pin is hashed without a copy of the list here.
void write_cd_digest(Writer& ar,const Bus& bus) {
    AudioCheckpointAccess::cd(ar,bus.cd);AudioCheckpointAccess::adpcm(ar,bus.adpcm);
}
void read_audio(Reader& ar,Bus& bus) {
    AudioCheckpointAccess::cd(ar,bus.cd);AudioCheckpointAccess::psg(ar,bus.psg);
    AudioCheckpointAccess::adpcm(ar,bus.adpcm);AudioCheckpointAccess::pcm(ar,bus.pcm,bus.cd.provider);
    validate_audio(bus);
}
} // namespace checkpoint
} // namespace pce
