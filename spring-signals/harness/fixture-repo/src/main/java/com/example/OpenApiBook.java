package com.example;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import io.swagger.annotations.ApiOperation;
import io.swagger.annotations.Api;

@Api
@Tag(name = "books")
public class OpenApiBook {
    @Operation(summary = "Get a book", description = "Fetches a book by id")
    @ApiResponse(responseCode = "200", description = "OK")
    public String getBook() {
        return "book";
    }

    @ApiOperation(value = "Create a book", notes = "Creates a book")
    public String createBook() {
        return "created";
    }
}
