const GeoLayout jimmie_orig_board_geo[] = {
    GEO_CULLING_RADIUS(450),
    GEO_OPEN_NODE(),
        GEO_ANIMATED_PART(LAYER_OPAQUE, 0, 0, 0, jimmie_orig_board_board_draw_dl),
        GEO_DISPLAY_LIST(LAYER_OPAQUE, jimmie_orig_board_revert_dl),
    GEO_CLOSE_NODE(),
    GEO_END(),
};
