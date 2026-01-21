"""Tests for the drive detection module."""


from dvdtoplex.drives import parse_drutil_output


class TestParseDrutilOutput:
    """Tests for parse_drutil_output function."""

    def test_parse_with_disc(self) -> None:
        """Should detect disc present with vendor and label."""
        output = """Vendor: MATSHITA
Product: DVD-R UJ-868
Revision: KB17
Type: CD-ROM
Media Inserted: Yes
Name: MY_DVD_MOVIE
"""
        vendor, has_disc, disc_label = parse_drutil_output(output)

        assert vendor == "MATSHITA"
        assert has_disc is True
        assert disc_label == "MY_DVD_MOVIE"

    def test_parse_without_disc(self) -> None:
        """Should detect when no disc is inserted."""
        output = """Vendor: MATSHITA
Product: DVD-R UJ-868
Revision: KB17
No Media Inserted
"""
        vendor, has_disc, disc_label = parse_drutil_output(output)

        assert vendor == "MATSHITA"
        assert has_disc is False
        assert disc_label is None

    def test_parse_no_disc_alternate(self) -> None:
        """Should handle alternate 'No disc inserted' message."""
        output = """Vendor: LG
Product: GDR-8163B
No disc inserted
"""
        vendor, has_disc, disc_label = parse_drutil_output(output)

        assert vendor == "LG"
        assert has_disc is False
        assert disc_label is None

    def test_parse_empty_output(self) -> None:
        """Should handle empty output."""
        vendor, has_disc, disc_label = parse_drutil_output("")

        assert vendor == ""
        assert has_disc is False
        assert disc_label is None

    def test_parse_disc_with_media_type(self) -> None:
        """Should detect disc when Type and Media are present."""
        output = """Vendor: PIONEER
Product: DVD-RW DVR-111D
Type: DVD-ROM
Media: DVD-ROM
Name: MOVIE_TITLE_2024
"""
        vendor, has_disc, disc_label = parse_drutil_output(output)

        assert vendor == "PIONEER"
        assert has_disc is True
        assert disc_label == "MOVIE_TITLE_2024"

    def test_parse_disc_with_special_characters(self) -> None:
        """Should handle disc labels with special characters."""
        output = """Vendor: MATSHITA
Type: DVD-ROM
Media: DVD-ROM
Name: MOVIE_PART_1_DISC_A
"""
        vendor, has_disc, disc_label = parse_drutil_output(output)

        assert has_disc is True
        assert disc_label == "MOVIE_PART_1_DISC_A"
