const GeoLayout jimmie_shadow_geo[] = {
    GEO_CULLING_RADIUS(450),
    GEO_OPEN_NODE(),
        GEO_SHADOW(SHADOW_CIRCLE_4_VERTS, 0x9B, 120),
        GEO_OPEN_NODE(),
            GEO_DISPLAY_LIST(LAYER_OPAQUE, jimmie_shadow_dl),
        GEO_CLOSE_NODE(),
    GEO_CLOSE_NODE(),
    GEO_END(),
};
