package com.example.fixture;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.ResponseBody;

/** Literal @Controller plus @RequestMapping(method = ...), the mapping_any shape. */
@Controller
@RequestMapping(path = "/legacy")
public class LegacyFixtureController {

  @RequestMapping(value = "/ping", method = RequestMethod.GET)
  @ResponseBody
  public String ping() {
    return "ok";
  }
}
