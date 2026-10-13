/* Firmware-free camera projection. The clipping bounds are algorithm
 * parameters, not a DSP program/data ROM. Polynomial coefficients are
 * synthesized from pi/4; no firmware lookup table is linked or loaded.
 * Numeric expectations come from authored cartridges under independent Snes9x.
 */
static int32_t rr_dsp1_axis(int16_t value,int32_t a,int32_t b) {
    /* -32768 * -32768 is +32768 in Q15. Keep the intermediate positive
     * until the outer multiply; narrowing it early reverses a projected axis. */
    return (int32_t)(((int64_t)value*((a*b)>>15))>>15);
}
static bool rr_dsp1_projection(Dsp1HleState *s,const int16_t *p,int16_t *out) {
    static const int16_t zenith_limit[16]={
        0x38b4,0x38b7,0x38ba,0x38be,0x38c0,0x38c4,0x38c7,0x38ca,
        0x38ce,0x38d0,0x38d4,0x38d7,0x38da,0x38dd,0x38e0,0x38e4
    };
    if(!s)return false;
    s->projection_valid=false;
    s->sin_aas=dsp1_sin((uint16_t)p[5]);
    s->cos_aas=dsp1_cos((uint16_t)p[5]);
    /* Original camera normal is kept for point/raster/target projection.
     * Only the ground-plane centre uses the clipped angle. */
    s->sin_azs=dsp1_sin((uint16_t)p[6]);
    s->cos_azs=dsp1_cos((uint16_t)p[6]);
    s->nx=q15_multiply(s->sin_azs,(int16_t)-(int32_t)s->sin_aas);
    s->ny=q15_multiply(s->sin_azs,s->cos_aas);
    s->nz=q15_multiply(s->cos_azs,INT16_MAX);
    int16_t x=(int16_t)(p[0]+q15_multiply(p[3],s->nx));
    int16_t y=(int16_t)(p[1]+q15_multiply(p[3],s->ny));
    int16_t z=(int16_t)(p[2]+q15_multiply(p[3],s->nz));
    s->gx=(int16_t)(x-q15_multiply(p[4],s->nx));
    s->gy=(int16_t)(y-q15_multiply(p[4],s->ny));
    s->gz=(int16_t)(z-q15_multiply(p[4],s->nz));
    s->les=p[4];s->les_exponent=0;
    normalize(s->les,&s->les_coefficient,&s->les_exponent);
    int16_t c,e=0;
    normalize(z,&c,&e);
    s->vplane_coefficient=c;s->vplane_exponent=e;
    if(e>0 || e < -15)return false;
    int16_t limit=zenith_limit[-e],angle=p[6];
    if(angle<0) {
        limit=(int16_t)-limit;
        if(angle<limit+1)angle=(int16_t)(limit+1);
    } else if(angle>limit)angle=limit;
    int16_t sine=dsp1_sin((uint16_t)angle),cosine=dsp1_cos((uint16_t)angle);
    inverse(cosine,0,&s->target_sec_coefficient,&s->target_sec_exponent);
    c=q15_multiply(c,s->target_sec_coefficient);
    normalize(c,&c,&e);e=(int16_t)(e+s->target_sec_exponent);
    c=q15_multiply(truncate_coefficient(c,e),sine);
    s->center_x=(int16_t)(x+q15_multiply(c,s->sin_aas));
    s->center_y=(int16_t)(y-q15_multiply(c,s->cos_aas));
    out[0]=0;
    if(p[6]!=angle || p[6]==limit) {
        int16_t zenith=p[6]==INT16_MIN ? INT16_MIN+1 : p[6];
        int16_t delta=(int16_t)(zenith-limit);
        if(delta>=0)delta=(int16_t)(delta-1);
        int16_t a=(int16_t)~((uint16_t)delta<<2);
        /* tan(t)=t+t^3/3; sec(t)=1+t^2/2+5t^4/24, t=a*pi/4.
         * Round Q15 coefficients, then retain each DSP word's truncation. */
        double unit=kPi/4.0;
        int16_t linear=(int16_t)lround(32768.0*unit);
        int16_t cubic=(int16_t)lround(32768.0*unit*unit*unit/3.0);
        int16_t quadratic=(int16_t)lround(32768.0*unit*unit/2.0);
        int16_t quartic=(int16_t)lround(32768.0*5.0*unit*unit*unit*unit/24.0);
        int16_t t=(int16_t)(q15_multiply(q15_multiply(a,cubic),a)+linear);
        out[0]=(int16_t)-(int32_t)q15_multiply(q15_multiply(t,a),p[4]);
        int16_t square=q15_multiply(a,a);
        t=(int16_t)(q15_multiply(square,quartic)+quadratic);
        cosine=(int16_t)(cosine+q15_multiply(q15_multiply(square,t),cosine));
    }
    s->v_offset=q15_multiply(p[4],cosine);
    int16_t sec;
    inverse(sine,0,&sec,&e);
    normalize(s->v_offset,&c,&e);
    normalize(q15_multiply(c,sec),&c,&e);
    if(c==INT16_MIN) {c>>=1;e++;}
    out[1]=truncate_coefficient((int16_t)-(int32_t)c,e);
    out[2]=s->center_x;out[3]=s->center_y;
    inverse(cosine,0,&s->sec_azs_coefficient,&s->sec_azs_exponent);
    s->projection_valid=true;
    return true;
}
