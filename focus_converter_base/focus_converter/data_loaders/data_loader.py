import io
from enum import Enum
from typing import Iterable

import polars as pl
import pyarrow.dataset as ds
from tqdm import tqdm

# these values need to be tweaked, for datasets with small number of columns,
# following values can be much larger.
# for very fragments with large number of row groups, this will cause memory to exhaust
DEFAULT_BATCH_READ_SIZE = 50000
FRAGMENT_READ_AHEAD = 0
BATCH_READ_AHEAD = 0


class DataFormats(Enum):
    CSV = "csv"
    PARQUET = "parquet"


class ParquetDataFormat(Enum):
    FILE = "file"
    DATASET = "dataset"
    DELTA = "delta"


class DataLoader:
    def __init__(
        self,
        data_path: str,
        data_format: DataFormats,
        parquet_data_format: ParquetDataFormat = None,
    ):
        self.__data_path__ = data_path
        self.__data_format__ = data_format
        self.__parquet_data_format__ = parquet_data_format

    def load_pyarrow_dataset(self) -> Iterable[pl.LazyFrame]:
        dataset = ds.dataset(self.__data_path__)
        scanner = dataset.scanner(
            batch_size=DEFAULT_BATCH_READ_SIZE,
            use_threads=True,
            fragment_readahead=FRAGMENT_READ_AHEAD,
            batch_readahead=BATCH_READ_AHEAD,
        )

        total_rows = dataset.count_rows()

        with tqdm(total=total_rows) as pobj:
            for batch in scanner.to_batches():
                df = pl.from_arrow(batch)

                # skip if number of rows empty
                if df.shape[0] == 0:
                    continue

                yield df.lazy()
                pobj.update(df.shape[0])

    def load_parquet_file(self) -> Iterable[pl.LazyFrame]:
        # reads parquet from data path and returns a lazy object

        yield pl.read_parquet(self.__data_path__).lazy()

    def load_csv(self) -> Iterable[pl.LazyFrame]:
        # reads csv from data path and returns a lazy object
        # IBM Cloud CSV's contain multiple sections separated by `\n\n`. Data contained in the first section acts as meta data.
        # To "normalize" the IBM Cloud CSV we duplicate the rows so that the data is concatenated for every row of the csv

        # Read the content of the file first to first figure out how many sections there are
        with open(self.__data_path__, "r") as f:
            content = f.read()

        # Handle empty files
        if not content or not content.strip():
            raise ValueError(f"CSV file is empty: {self.__data_path__}")

        # Split the CSV content into sections
        sections = content.split("\n\n")

        # Handle single-section (standard) CSV case
        if len(sections) == 1:
            yield pl.read_csv(
                io.StringIO(sections[0]),
                try_parse_dates=False,
                ignore_errors=True,
                truncate_ragged_lines=True,
            ).lazy()
            return

        # Process the last section separately. Which contains the main content. In the case of a traditional CSV this is what gets returned
        df_last_section = pl.read_csv(
            io.StringIO(sections[len(sections) - 1]),
            try_parse_dates=False,
            ignore_errors=True,
            truncate_ragged_lines=True,
        )

        # For each section before the final section. Duplicate the rows and concatenate the data to the main content from the last section
        for i in range(0, len(sections) - 1):
            # Skip empty sections
            if not sections[i].strip():
                continue

            # Parse the new section
            df_current_section = pl.read_csv(
                io.StringIO(sections[i]),
                try_parse_dates=False,
                ignore_errors=True,
                truncate_ragged_lines=True,
            )

            # Skip if no rows to duplicate
            if df_last_section.height == 0 or df_current_section.height == 0:
                continue

            # duplicate the data
            df_current_section_repeated = df_current_section.select(
                pl.all().repeat_by(df_last_section.height).explode()
            )

            # Concatenate the data with the last section
            df_last_section = pl.concat(
                [df_current_section_repeated, df_last_section], how="horizontal"
            )

        yield df_last_section.lazy()

    def data_scanner(self) -> Iterable[pl.LazyFrame]:
        # helper function to read from different data formats and create an iterator of lazy frames
        # which then can be used to apply lazy eval plans

        if self.__data_format__ == DataFormats.CSV:
            yield from self.load_csv()
        elif self.__data_format__ == DataFormats.PARQUET:
            if self.__parquet_data_format__ == ParquetDataFormat.FILE:
                yield from self.load_parquet_file()
            elif self.__parquet_data_format__ == ParquetDataFormat.DATASET:
                yield from self.load_pyarrow_dataset()
            else:
                raise NotImplementedError(
                    f"Parquet format:{self.__parquet_data_format__} not implemented"
                )
        else:
            raise NotImplementedError(
                f"Data format:{self.__data_format__} not implemented"
            )
